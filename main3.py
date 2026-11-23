import os
import streamlit as st

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from supabase import create_client, Client
from typing import Literal, Union

# streamlit run main3.py

# open ai key
api_key = "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"

# set up supabase
url: str = "https://iujbwzxyczsudnqjglvg.supabase.co"
key: str = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Iml1amJ3enh5Y3pzdWRucWpnbHZnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzkyODg2MzksImV4cCI6MjA5NDg2NDYzOX0.RigJxtCXzIvKaTZWojhImobHZhUmZkGrsIkNWBA4lzU"

supabase: Client = create_client(url, key)


st.title("🤖 AI Customer Support Agent")

# ==========================================
# 1. DEFINE INDEPENDENT BACKEND TOOLS
# ==========================================
@tool
def track_order(order_id: str) -> str:
    """Call this tool when the user wants to check the status or tracking details of an order number."""
    # Mock data lookup
    return f"📦 System Status for Order {order_id}: In Transit. Carrier: FedEx. Expected Delivery: Friday."

@tool
def cancel_order(order_id: str, reason: str = "Not provided") -> str:
    """Call this tool when the user explicitly requests to cancel an order."""
    return f"❌ System Action: Order {order_id} has been successfully flagged for cancellation. Reason: {reason}."

@tool
def get_product_info(keyword: Literal["protein", "greens", "energy"]) -> str:
    """
    Search the database by a strict product keyword.
    Use this tool whenever the user is looking for a specific type of supplement, 
    fitness goal (like protein, mass, energy), or product name.
    Use 'protein' for muscle/gym, 'greens' for veg/health, and 'energy' for pre-workout.
    """
    try:
        
        response = (
            supabase.table("products")
            .select("*")
            .or_(f"product_name.ilike.%{keyword}%,product_info.ilike.%{keyword}%")
            .eq("category", keyword)
            .execute()
            )
        
        products = response.data
        
        if not products:
            return f"No products found matching the keyword '{keyword}'."
        
        # Format the database rows cleanly so the LLM can read them easily
        results = []
        for p in products:
            results.append(f"- ID: {p.get('id')} | Name: {p.get('product_name')} | Price: ${p.get('price')} | Desc: {p.get('product_info', 'N/A')}")
        
        return "\n".join(results)
        
    except Exception as e:
        return f"Error accessing database: {str(e)}"

@tool
def process_refund_subversion(order_id: str, issue_description: str) -> str:
    """Call this tool when a user complains about a product or demands a refund. Evaluates eligibility based on description."""
    if "broken" in issue_description.lower() or "damaged" in issue_description.lower():
        return f"💰 Refund Approved: Order {order_id} flagged for immediate 100% refund due to product damage."
    return f"⚠️ Refund Pending: Order {order_id} routing to human review. Action required: user must upload photo evidence."

# Group all available tools into an executable map
tools_list = [track_order, cancel_order, get_product_info, process_refund_subversion]
tools_map = {tool.name: tool for tool in tools_list}

# ==========================================
# 2. CHAT MEMORY PERSISTENCE
# ==========================================
# Initialize conversational memory using true LangChain Message objects
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# Redraw conversational interface history layout on refresh
for message in st.session_state.chat_history:
    if isinstance(message, HumanMessage):
        with st.chat_message("user"):
            st.write(message.content)
    elif isinstance(message, AIMessage) and message.content:
        with st.chat_message("assistant"):
            st.write(message.content)

# ==========================================
# 3. INTERACTIVE CONVERSATION EXECUTION
# ==========================================
user_prompt = st.chat_input("How can I assist you today?")

if user_prompt:
    # Render user prompt bubble immediately
    with st.chat_message("user"):
        st.write(user_prompt)
    st.session_state.chat_history.append(HumanMessage(content=user_prompt))

    # Construct system instructions with context tracking capabilities
    prompt_template = ChatPromptTemplate.from_messages([
        ("system", """You are a highly adaptable, multi-purpose customer support agent. 
        Users will often present multiple requests or goals at the exact same time, or switch topics mid-conversation.
        
        Guidelines:
        1. If the user presents multiple actions (e.g., tracking a package AND asking about a job), call ALL matching tools simultaneously in a single turn.
        2. If the user is browsing or trying to find a perfect product, answer them conversationsally using text.
        3. Never tell the user you are calling a tool; simply execute it.
        """),
        MessagesPlaceholder(variable_name="history"),
        ("user", "{input_prompt}")
    ])

    # Instantiate LLM and explicitly bind the tools array to it
    llm = ChatOpenAI(model="gpt-5.2", api_key=api_key)
    llm_with_tools = llm.bind_tools(tools_list)
    
    chain = prompt_template | llm_with_tools

    with st.spinner("Agent analyzing intents and actions..."):
        # Invoke LLM with complete contextual chat memory payload
        ai_message = chain.invoke({
            "history": st.session_state.chat_history[:-1],
            "input_prompt": user_prompt
        })

    # Render Assistant's response
    with st.chat_message("assistant"):
        # Write any conversational text the AI generated
        if ai_message.content:
            st.write(ai_message.content)
            
        st.session_state.chat_history.append(ai_message)

        # Handle tool calling sequences
        if ai_message.tool_calls:
            for tool_call in ai_message.tool_calls:
                # Find the matched python function
                selected_tool = tools_map[tool_call["name"]]
                
                # Execute the function live using arguments provided by the LLM
                with st.status(f"🛠️ Executing: {tool_call['name']}()", expanded=True):
                    st.caption(f"Arguments parsed by AI: {tool_call['args']}")
                    tool_output = selected_tool.invoke(tool_call["args"])
                    st.write(tool_output)

                # Save tool execution result back into memory history so the LLM retains visibility
                st.session_state.chat_history.append(
                    ToolMessage(content=str(tool_output), tool_call_id=tool_call["id"])
                )
