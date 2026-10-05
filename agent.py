


import json
from pprint import pprint
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from langchain.agents import create_agent
from langchain_groq import ChatGroq
from langchain_openrouter import ChatOpenRouter
from langchain_nvidia_ai_endpoints import ChatNVIDIA

from fastapi import FastAPI,HTTPException
import sqlite3 

load_dotenv()
class SqlBody(BaseModel):
    sql:str

class Question(BaseModel):
    question:str

class SQLResponse(BaseModel):
    thought_process: str = Field(
        description="Step-by-step reasoning on joins, filters, and aggregations used."
    )
    sql: str = Field(description="The executable SQLite query.")
    explanation: str = Field(
        description="A brief, non-technical description of the results retrieved."
    )


# 2. Helper function to load JSON files
def load_json(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


# Load prompt data
# user_data = load_json("input.json")
sys_data = load_json("sys_prompt.json")

# user_content = user_data["content"]
system_content = (
    json.dumps(sys_data, indent=2)
    if isinstance(sys_data, dict)
    else str(sys_data)
)

# 3. Initialize Model and Agent
llm = ChatGroq(
    # model = 'qwen/qwen3.8-27b'
    model = 'openai/gpt-oss-20b'
)
# llm = ChatOpenRouter(model="openrouter/free")
# llm = ChatNVIDIA(model="nvidia/nemotron-3-ultra-550b-a55b",
#                     model_kwargs={"chat_template_kwargs": {"enable_thinking": True}},
#                    )

agent = create_agent(
    model=llm,
    tools=[],  # Pass list of tools if any are needed
    response_format=SQLResponse,
)

# 4. Execute Agent with system message context and user query
# messages = [
#     {"role": "system", "content": system_content},
#     {"role": "user", "content": user_content},
# ]

# result = agent.invoke({"messages": messages})

# 5. Extract structured output from `structured_response`
# structured_output: SQLResponse = result["structured_response"]
# output_dict = structured_output.model_dump()

# print("Parsed LLM Output:")
# pprint(output_dict)

# # 6. Save result to output.json
# with open("output.json", "w", encoding="utf-8") as f:
#     json.dump(output_dict, f, indent=4)

# print("\nResult successfully saved to output.json")

app = FastAPI()

@app.post("/ask")
def ask(body : Question):
    result = agent.invoke({"messages":[
        {"role":'system',"content":system_content},
        {"role":'user',"content":body.question}
    ]})

    

    answer = result['structured_response'].model_dump()
    try:
        answer['result'] = run_sql(SqlBody(sql=answer["sql"]))
    except HTTPException as e:
        answer['sql_error'] = e.detail

    pprint(answer)
    return answer

@app.post("/sql")
def run_sql(body:SqlBody):
    try:
        conn = sqlite3.connect('file:longlist.db?mode=ro',uri=True)
        cur = conn.execute(body.sql)
        rows = cur.fetchmany(100)
        col = [c[0] for c in cur.description]
        conn.close()
    except Exception as e:
        raise HTTPException(status_code=400,detail=str(e))
    return {'columns':col,'rows':rows}


    