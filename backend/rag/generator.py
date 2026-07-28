import os
import json
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
MODEL_NAME = "llama-3.3-70b-versatile"

def generate_answer(question: str, context: str, history: list[dict] = None) -> dict:
    """
    Generate a structured analysis using Groq JSON mode.
    Returns a dict with: root_cause_analysis, recommendation, risk_assessment, final_response.
    """
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY is not set.")

    client = Groq(api_key=GROQ_API_KEY)

    system_prompt = (
        "You are an elite Azure Cloud Incident AI Assistant.\n"
        "Your role is to help Site Reliability Engineers (SREs) diagnose and resolve infrastructure issues.\n\n"
        "RULES:\n"
        "1. Base your answer ONLY on the provided Context and Conversation History.\n"
        "2. ALWAYS cite your sources using the rich metadata provided in the Context chunks (e.g. 'According to Incident 1523...').\n"
        "3. You MUST return your response as a JSON object with exactly these four keys:\n"
        "   - \"root_cause_analysis\": A detailed explanation of the likely failure.\n"
        "   - \"recommendation\": Immediate actionable steps the SRE should take.\n"
        "   - \"risk_assessment\": An evaluation of the severity or risk based on historical data.\n"
        "   - \"final_response\": A concise summary wrapping up the analysis.\n"
        "4. If the Context does not contain the answer, state that in all four fields."
    )

    history_text = ""
    if history:
        history_lines = ["\n[Conversation History]"]
        for turn in history:
            role = "User" if turn["role"] == "user" else "Assistant"
            # History now contains complex assistant responses, just stringify them for context
            content_str = str(turn["content"]) if isinstance(turn["content"], dict) else turn["content"]
            history_lines.append(f"{role}: {content_str}")
        history_lines.append("────────────────────────────────────────\n")
        history_text = "\n".join(history_lines)

    user_prompt = (
        f"[Retrieved Context]\n{context}\n\n"
        f"────────────────────────────────────────\n"
        f"{history_text}"
        f"[Current Question]\n{question}"
    )

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.2,
            max_tokens=2048,
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content
        return json.loads(content)
    except Exception as e:
        print(f"[Generator] Error calling Groq: {e}")
        raise e
