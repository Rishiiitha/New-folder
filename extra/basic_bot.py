import os
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableParallel, RunnablePassthrough
from langchain_ollama import OllamaLLM
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_postgres import PGVector

# --- 1. Setup Database Connection ---
# Make sure to update this with your real details
DB_CONNECTION_STRING = "postgresql+psycopg://postgres:Veeraragava@localhost:5432/Knowledge_base"
COLLECTION_NAME = "New_embeddings"

# --- 2. Initialize Components ---

print("Initializing models and embeddings...")
llm = OllamaLLM(model="llama3.1")
embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

print("Setting up vector store...")
# Connect to your existing PGVector store
try:
    store = PGVector(
        connection=DB_CONNECTION_STRING,
        collection_name=COLLECTION_NAME,
        embeddings=embeddings, 
    )
    
    retriever = store.as_retriever(
        search_type="similarity",
        search_kwargs={"k": 5}
    )
    print("Vector store connected successfully.")

except Exception as e:
    print(f"Error connecting to vector store: {e}")
    print("Please ensure your PostgreSQL server is running, the 'pgvector' extension is enabled,")
    print("and the connection string is correct and uses the 'psycopg' driver.")
    exit()


# --- 3. Define the RAG Chain using LCEL ---

#
# *** THIS IS THE MISSING FUNCTION ***
#
def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)

# NEW, STRICT, VOICE-READY TEMPLATE
template = """
You are a helpful AI assistant for a college, answering questions for students and parents.
You MUST follow these rules in EVERY response:

**Rule 1: Use Context ONLY**
- Your ONLY source of information is the 'Context' provided below.
- You must ONLY answer based on the information in the 'Context'.
- **NEVER** use any of your outside general knowledge. Do not make up facts.
- If the 'Context' does not contain the information needed to answer the 'Question', you **MUST** say *exactly*: 
  "I'm sorry, I don't have that information in the college database. Please ask another question."

**Rule 2: Format for Voice (Text-to-Speech)**
- **NEVER** use bullet points, asterisks (*), lists, or any markdown formatting.
- You must write everything as a single, natural paragraph, as if you are speaking.
- You must spell out acronyms. For example, if you see 'BIT', you must write 'B I T'. If you see 'VTU', you must write 'V T U'.
- You must read phone numbers digit by digit. For example, '9876543210' must be written as 'nine eight seven six five four three two one zero'.

**Rule 3: Be Concise**
- **Keep your answers short and conversational.**
- Do not provide extra details unless the user asks for them.
- Get straight to the point.

---
Context:
{context}

Question:
{question}

Answer:
"""
prompt = ChatPromptTemplate.from_template(template)

print("Building RAG chain...")
# This line will now work because format_docs is defined above
rag_chain = (
    RunnableParallel(
        context=(retriever | format_docs), 
        question=RunnablePassthrough()
    )
    | prompt
    | llm
    | StrOutputParser()
)

print("Chatbot is ready! Type 'exit' to quit.\n")


# --- 4. Run the Chatbot ---

# Define conversational words to intercept
filler_inputs = {
    "ok": "Got it. Do you have another question?",
    "okay": "Got it. Do you have another question?",
    "thanks": "You're welcome! Is there anything else I can help with?",
    "thank you": "You're welcome! Is there anything else I can help with?",
    "got it": "Great. Let me know if you have any other questions."
}

while True:
    try:
        query = input("You: ")
        
        if query.lower() == 'exit':
            break
        
        # Check if the input is a simple filler word
        clean_query = query.lower().strip(" .!")
        if clean_query in filler_inputs:
            print(f"\nBot: {filler_inputs[clean_query]}\n")
            continue  # Skip the RAG chain and ask for new input

        if not query.strip():
            continue

        print("\nBot: ", end="", flush=True)
        
        for chunk in rag_chain.stream(query):
            print(chunk, end="", flush=True)
        
        print("\n")

    except KeyboardInterrupt:
        print("\nExiting...")
        break
    except Exception as e:
        print(f"\nAn error occurred: {e}")