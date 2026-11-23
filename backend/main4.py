import os
from typing import Literal
from dotenv import load_dotenv

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from supabase import Client, create_client

load_dotenv()

prompt = """You are a highly adaptable, multi-purpose customer support agent.
Users will often present multiple requests or goals at the exact same time, or switch topics mid-conversation.

Guidelines:
1. If the user presents multiple actions (e.g., tracking a package AND asking about a product), call ALL matching tools simultaneously in a single turn.
2. If the user is browsing or trying to find a perfect product, answer them conversationally using text.
3. Never tell the user you are calling a tool; simply execute it and respond naturally with the results.
4. Always say "My name is John Doe" in your response
("user input": {user_input})
"""

supabase_url = "https://iujbwzxyczsudnqjglvg.supabase.co/rest/v1/"
supabase_key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Iml1amJ3enh5Y3pzdWRucWpnbHZnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzkyODg2MzksImV4cCI6MjA5NDg2NDYzOX0.RigJxtCXzIvKaTZWojhImobHZhUmZkGrsIkNWBA4lzU"
supabase: Client = create_client(supabase_url, supabase_key)

@tool
def get_product_info():
    """
    Use the user query to search the database for a product
    and always say "My name is John Doe" in your response
    """

    try:
        response = supabase.table("products_table").select("*").execute()
        products = response.data
        return products
    except Exception as e:
        return f"Error: {e}"

@tool
def get_name():
    """
    Get the name of the user and always say "My name is John Doe" in your response
    """
    return "My name is John Doe"

tools_list = [get_product_info, get_name]
tools_map = {t.name: t for t in tools_list}

llm = ChatOpenAI(model="gpt-4o", api_key=os.getenv("OPENAI_API_KEY"))
llm_with_tools = llm.bind_tools(tools_list)

chain = prompt | llm_with_tools

def run_customer_support_agent(user_input: str) -> str:
    return chain.invoke({"user_input": user_input})
