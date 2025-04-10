# agents/snowflake_agent.py
import os
import pandas as pd
import numpy as np  # Add numpy import
import matplotlib.pyplot as plt
from sqlalchemy import create_engine
from langchain.tools import Tool
from langchain.agents import AgentType, initialize_agent
from langchain_anthropic import ChatAnthropic
from dotenv import load_dotenv
import warnings
from io import BytesIO
import base64
import time
from typing import Dict, Any

# Suppress deprecation warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

# Load environment variables
load_dotenv(override=True)

# Initialize Snowflake SQLAlchemy engine
engine = create_engine(
    f"snowflake://{os.environ.get('SNOWFLAKE_USER')}:{os.environ.get('SNOWFLAKE_PASSWORD')}@{os.environ.get('SNOWFLAKE_ACCOUNT')}/{os.environ.get('SNOWFLAKE_DATABASE')}/{os.environ.get('SNOWFLAKE_SCHEMA')}?warehouse={os.environ.get('SNOWFLAKE_WAREHOUSE')}"
)
 

 
def get_valuation_summary(query:str=None) -> dict:
    """Get NVIDIA valuation metrics visualization"""
    try:
        # Use base query
        df = pd.read_sql("SELECT * FROM Valuation_Measures ORDER BY DATE DESC LIMIT 5", engine)
        df.columns = df.columns.str.upper().str.strip()
        
        if df.empty:
            raise ValueError("No data returned from Snowflake. Ensure the table contains data.")
        
        # Generate visualization
        plt.figure(figsize=(10, 6))
        for date in df["DATE"].unique():
            subset = df[df["DATE"] == date]
            plt.bar(subset.columns[1:], subset.iloc[0, 1:], label=str(date))
        
        plt.xlabel("Metric")
        plt.ylabel("Value")
        plt.title("NVIDIA Valuation Metrics")
        plt.xticks(rotation=45)
        plt.legend()
        
        # Convert plot to base64
        buf = BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight')
        buf.seek(0)
        img_str = base64.b64encode(buf.getvalue()).decode()
        
        return {
            "chart": img_str,
            "summary": df.to_string(),
            "status": "success"
        }
        
    except Exception as e:
        return {
            "error": str(e),
            "status": "failed"
        }
def get_graph_specs_from_llm(data: pd.DataFrame,model_name:str) -> dict:
    """Get graph specifications from LLM based on the Snowflake data."""
    try:
        # Convert DataFrame to a JSON-like string for LLM input
        data_summary = data.to_dict(orient="list")
        prompt = f"""
        Based on the following NVIDIA financial data:
        {data_summary}
        Generate a graph specification in this format:
        - Title: [Graph title]
        - Type: [line/bar/scatter]
        - X-axis: [label and settings]
        - Y-axis: [label and settings]
        - Colors: [color scheme]
        - Additional elements: [grid, legend position, etc.]

        Focus on making the graph visually informative and easy to interpret.
        """
        llm = initialize_llm(model_name)
        # Send the prompt to the LLM
        response = llm.invoke(prompt)
        if not response or not hasattr(response, "content"):
            raise ValueError("LLM did not return a valid response.")
        
        # Extract the content from the AIMessage object
        if hasattr(response, "content"):
            response_text = response.content
        else:
            response_text = str(response)
        
        # Parse the LLM response into a dictionary
        specs = {}
        for line in response_text.split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                specs[key.strip()] = value.strip()
        
        return specs
    except Exception as e:
        print(f"Error getting graph specs from LLM: {str(e)}")
        return {}

def create_graph_from_llm_specs(data: pd.DataFrame, specs: dict) -> str:
    """Create a stacked area graph based on LLM specifications with normalized values."""
    try:
        if 'DATE' not in data.columns:
            raise ValueError("The 'DATE' column is missing from the data.")
        
        # Create a copy of the DataFrame for normalization
        df_normalized = data.copy()
        
        # Normalize all numeric columns except DATE
        for col in df_normalized.columns:
            if col != 'DATE':
                min_val = df_normalized[col].min()
                max_val = df_normalized[col].max()
                if max_val - min_val != 0:  # Avoid division by zero
                    df_normalized[col] = (df_normalized[col] - min_val) / (max_val - min_val)
        
        # Create figure with larger size to accommodate legend
        plt.figure(figsize=(15, 8))
        x = pd.to_datetime(df_normalized["DATE"]).dt.strftime('%b %d, %Y')  # Format dates for better readability
        
        # Determine the graph type
        graph_type = specs.get("Type", "stacked").lower()  # Default to "stacked"
        y_label = specs.get("Y-axis", "Normalized Value (0-1 scale)")
        title = f"{specs.get('Title', 'NVIDIA Financial Metrics')} (Normalized)"
        
        # Define color palette
        colors = plt.cm.Set2(np.linspace(0, 1, len(df_normalized.columns[1:])))
        
        # Plot the graph based on the type
        if graph_type == "stacked":
            # Prepare data for stacked area plot
            y_values = df_normalized[df_normalized.columns[1:]].T.values
            plt.stackplot(x, y_values, labels=[col.replace('_', ' ').title() for col in df_normalized.columns[1:]], colors=colors, alpha=0.8)
        else:
            # Fallback to line plot if graph type is not "stacked"
            for idx, col in enumerate(df_normalized.columns[1:]):
                plt.plot(x, df_normalized[col], 
                         label=f"{col.replace('_', ' ').title()}",  # Make column names more user-friendly
                         marker="o", 
                         color=colors[idx], 
                         linewidth=2)
        
        # Apply formatting
        plt.title(title, fontsize=16, pad=20)
        plt.xlabel(specs.get("X-axis", "Date"), fontsize=14)
        plt.ylabel(y_label, fontsize=14)
        plt.grid(True, alpha=0.3, linestyle='--')
        
        # Add legend with better formatting
        plt.legend(
            loc='upper left',
            bbox_to_anchor=(1.05, 1),
            fontsize=12,
            title='Metrics',
            title_fontsize=14,
            frameon=True,
            fancybox=True,
            shadow=True
        )
        
        # Rotate x-axis labels for better readability
        plt.xticks(rotation=45, ha="right", fontsize=12)
        plt.yticks(fontsize=12)
        
        # Adjust layout to prevent legend cutoff
        plt.tight_layout()
        
        # Save the graph
        chart_file_path = "llm_generated_graph.png"
        plt.savefig(
            chart_file_path,
            format="png",
            dpi=150,
            bbox_inches="tight",
            pad_inches=0.5
        )
        plt.close()
        
        return chart_file_path
    except Exception as e:
        print(f"Error creating graph: {str(e)}")
        return None
def get_valuation_summary_with_llm_graph(model_name:str = "claude-3-haiku-20240307") -> dict:
    """Get NVIDIA valuation metrics and generate a graph using LLM."""
    try:
        # Fetch data from Snowflake
        df = pd.read_sql("SELECT * FROM Valuation_Measures ORDER BY DATE ASC LIMIT 10", engine)
        
        # Normalize column names
        df.columns = df.columns.str.upper().str.strip()
        
        if df.empty:
            raise ValueError("No data returned from Snowflake. Ensure the table contains data.")
        
        # Ensure the DATE column is parsed as datetime
        if 'DATE' in df.columns:
            df['DATE'] = pd.to_datetime(df['DATE'], errors='coerce')
            if df['DATE'].isnull().all():
                raise ValueError("The 'DATE' column could not be parsed as datetime.")
        else:
            raise ValueError("The 'DATE' column is missing from the data.")
        
        # Get graph specifications from LLM
        graph_specs = get_graph_specs_from_llm(df,model_name)
        if not graph_specs:
            print("LLM failed to generate graph specifications. Using default graph settings.")
            graph_specs = {
                "Title": "Default Graph",
                "Type": "line",
                "X-axis": "Date",
                "Y-axis": "Value",
                "Additional elements": "grid, legend"
            }
        
        # Create the graph based on LLM specifications
        chart_file_path = create_graph_from_llm_specs(df, graph_specs)
        if not chart_file_path:
            raise ValueError("Failed to create graph from LLM specifications.")
        
        # Return the summary and graph path
        return {
            "summary": df.to_dict(orient="records"),
            "chart_path": chart_file_path,
            "graph_specs": graph_specs,
            "status": "success"
        }
    except Exception as e:
        print(f"Error in get_valuation_summary_with_llm_graph: {str(e)}")
        return {
            "error": str(e),
            "status": "failed"
        }

def initialize_llm(model_name="claude-3-haiku-20240307"):
    """Initialize LLM based on model name."""
    # Initialize the appropriate LLM based on the model name
    if "claude" in model_name:
        llm = ChatAnthropic(
            model=model_name,
            temperature=0,
            anthropic_api_key=os.environ.get('ANTHROPIC_API_KEY')
        )
    elif "gemini" in model_name:
        from langchain_google_genai import ChatGoogleGenerativeAI
        llm = ChatGoogleGenerativeAI(
            model=model_name,
            temperature=0,
            google_api_key=os.environ.get('GEMINI_API_KEY')
        )
    elif "deepseek" in model_name:
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(
            model=model_name,
            temperature=0,
            api_key=os.environ.get('DEEP_SEEK_API_KEY')
        )
    elif "grok" in model_name:
        from langchain_groq import ChatGroq
        llm = ChatGroq(
            model=model_name,
            temperature=0,
            api_key=os.environ.get('GROK_API_KEY')
        )
    else:
        llm = ChatAnthropic(
            model="claude-3-haiku-20240307",
            temperature=0,
            anthropic_api_key=os.environ.get('ANTHROPIC_API_KEY')
        )
    return llm
 
def get_ai_analysis_with_graph(prompt: str, model_name: str = "claude-3-haiku-20240307"):
    """Get AI-generated analysis of NVIDIA metrics with LLM-generated graph."""
    try:
        # Get the valuation summary and graph
        result = get_valuation_summary_with_llm_graph(model_name=model_name)
        if result["status"] == "failed":
            return {"status": "failed", "error": result['error']}
        
        # Create a prompt for the LLM to analyze the data and graph
        llm_prompt = f"""
        Analyze the following NVIDIA financial data and the generated graph:
        Data Summary:
        {result['summary']}
        
        Graph Specifications:
        {result['graph_specs']}
        
        Provide insights based on the data and the graph. Highlight key trends, patterns, and any significant observations.
        """
        llm = initialize_llm(model_name)
        # Get the analysis from the LLM
        response = llm.invoke(llm_prompt)
        
        # Handle the AIMessage response correctly
        if hasattr(response, 'content'):
            analysis = response.content
        else:
            analysis = str(response)
        
        # Always ensure chart_path is included in the response
        chart_path = result.get('chart_path', 'llm_generated_graph.png')
        
        # Make sure the chart file exists
        if not os.path.exists(chart_path):
            print(f"Warning: Chart path not found: {chart_path}")
            # Try to use default location as fallback
            if os.path.exists('llm_generated_graph.png'):
                chart_path = 'llm_generated_graph.png'
        
        return {
            "status": "success",
            "analysis": analysis,
            "chart_path": chart_path,  # Ensure chart path is included
            "summary": result.get('summary', {}),
            "graph_specs": result.get('graph_specs', "")
        }
    except Exception as e:
        print(f"Error during AI analysis with graph: {str(e)}")
        return {"status": "failed", "error": f"Analysis unavailable - {str(e)}"} 
 
 
 
if __name__ == "__main__":
    analysis = get_ai_analysis_with_graph(
        prompt="Analyze NVIDIA financial metrics using the nvidia_financial_metrics tool.Provide a brief summary of key insights.",
        model_name="gemini-2.0-flash"
    )
    print(analysis["analysis"])