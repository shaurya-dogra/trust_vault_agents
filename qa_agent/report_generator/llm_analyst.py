import json
import concurrent.futures
from langchain_ollama import ChatOllama

# Setup LLM model
llm = ChatOllama(
    model="qwen3-coder-next:cloud",
    base_url="http://localhost:11434",
    temperature=0.2,
    timeout=30.0,
)

def _extract_json(text: str) -> dict:
    """Helper to safely extract JSON, stripping markdown fences if present."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return json.loads(text.strip())

def _call_llm_json(prompt: str, fallback_value: dict) -> dict:
    """Invokes LLM and tries to parse JSON, with 1 retry and a fallback."""
    try:
        response = llm.invoke(prompt)
        content = response.content
        
        # Try parse 1
        try:
            return _extract_json(content)
        except json.JSONDecodeError:
            # Retry 1
            retry_prompt = f"{prompt}\n\nYour previous response failed to parse as JSON. Please return ONLY valid JSON.\n\nPrevious response:\n{content}"
            response2 = llm.invoke(retry_prompt)
            content2 = response2.content
            return _extract_json(content2)
    except Exception as e:
        print(f"LLM Call failed or rejected JSON parsing: {str(e)}")
        return fallback_value

def get_executive_summary(qa_report: dict) -> str:
    prompt = f"""You are a technical project manager writing a QA evaluation summary for an escrow platform.
Analyse this QA report JSON and write a 2-3 sentence executive summary.
Be specific — mention the milestone name, score, domains evaluated, and any notable findings.
Tone: professional, factual, concise.

QA Report:
{json.dumps(qa_report)}

Return ONLY JSON: {{"executive_summary": "string"}}"""

    score = qa_report.get("completion_score", 0)
    status = qa_report.get("status", "unknown")
    milestone_id = qa_report.get("milestone_id", "unknown")
    
    fallback = {"executive_summary": f"Automated evaluation of Milestone {milestone_id}. Score: {score}/100. Status: {status}."}
    
    result = _call_llm_json(prompt, fallback)
    return result.get("executive_summary", fallback["executive_summary"])

def get_domain_narrative(domain: str, domain_data: dict) -> str:
    prompt = f"""Analyse the domain report for the {domain} domain in this QA data.
Write a 1-2 sentence narrative explaining what was found, what passed, what failed, 
and what the confidence level means. Be specific about tool findings.
Reference actual values from the data (e.g. "8/8 tests passed", "35.0 seconds").

Domain data:
{json.dumps(domain_data)}

Return ONLY JSON: {{"narrative": "string"}}"""

    criteria_count = len(domain_data.get("criteria_results", []))
    conf = int(domain_data.get("agent_confidence", 0) * 100)
    fallback = {"narrative": f"Domain analysis complete. {criteria_count} criteria evaluated. Confidence: {conf}%."}
    
    result = _call_llm_json(prompt, fallback)
    return result.get("narrative", fallback["narrative"])

def get_recommended_actions(qa_report: dict) -> list:
    prompt = f"""Analyse this QA report and produce a prioritised list of recommended actions.
Each action must: state the priority (critical/high/medium/low), name the domain it applies to,
and give a specific actionable instruction referencing actual values from the report.
Do not make up findings — only reference what is in the data.

QA Report:
{json.dumps(qa_report)}

Return ONLY JSON:
{{"actions": [
  {{"priority": "critical|high|medium|low", "domain": "string", "title": "string", "detail": "string"}}
]}}"""
    
    fallback = {"actions": [{"priority": "low", "domain": "all", "title": "Review QA report", "detail": "Review the full evaluation report for this milestone."}]}
    
    result = _call_llm_json(prompt, fallback)
    return result.get("actions", fallback["actions"])

def get_verdict(qa_report: dict) -> dict:
    score = qa_report.get("completion_score", 0)
    status = qa_report.get("status", "unknown")
    
    # Calculate criteria met/total
    met = 0
    total = 0
    for dr in qa_report.get("domain_reports", []):
        for cr in dr.get("criteria_results", []):
            total += 1
            if cr.get("met"):
                met += 1
                
    prompt = f"""Write a single formal verdict sentence for this QA evaluation.
Include: score, status, number of criteria evaluated, payment recommendation.
This will appear as the closing statement of a legal-adjacent escrow evaluation report.

QA Report summary: score={score}, status={status}, criteria_met={met}/{total}

Return ONLY JSON: {{"verdict": "string", "payment_action": "string"}}"""

    payment_action = "Release payment" if score >= 85 and status == "completed" else "Hold payment"
    fallback = {
        "verdict": f"Evaluation complete. Final score: {score}/100. Status: {status}.",
        "payment_action": payment_action
    }
    
    result = _call_llm_json(prompt, fallback)
    if "verdict" not in result or "payment_action" not in result:
        return fallback
    return result

def analyse_report(qa_report: dict) -> dict:
    """
    Main entry point for llm analysis. Fetches all required LLM narratives.
    Returns a dict with:
    - executive_summary
    - domain_narratives (dict mapping domain -> narrative)
    - actions (list of action dicts)
    - verdict (dict with verdict and payment_action strings)
    """
    narratives = {}
    
    def fetch_domain_narrative_wrapper(dr):
        dom = dr.get("domain", "unknown")
        return dom, get_domain_narrative(dom, dr)
        
    # Execute LLM calls concurrently as they are purely I/O bound
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_exec = executor.submit(get_executive_summary, qa_report)
        future_actions = executor.submit(get_recommended_actions, qa_report)
        future_verdict = executor.submit(get_verdict, qa_report)
        
        domain_futures = [executor.submit(fetch_domain_narrative_wrapper, dr) for dr in qa_report.get("domain_reports", [])]
        
        exec_summary = future_exec.result()
        actions = future_actions.result()
        verdict = future_verdict.result()
        
        for f in domain_futures:
            dom, nar = f.result()
            narratives[dom] = nar
            
    return {
        "executive_summary": exec_summary,
        "domain_narratives": narratives,
        "actions": actions,
        "verdict": verdict
    }
