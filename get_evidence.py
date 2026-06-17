import os
import asyncio
from dotenv import load_dotenv
from groq import Groq
from crewai.flow.flow import Flow, listen, start
from crewai_tools import SerperDevTool

load_dotenv()
groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
search_tool = SerperDevTool()

def ask_groq(prompt: str) -> str:
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
        max_tokens=4000,
    )
    return response.choices[0].message.content

class ResearchFlow(Flow):
    
    # 1. Historian: Market Data Analysis - 2022-2026 Software Engineer Hiring Trends
    def gather_market_facts(self):
        print("▶️ Historian: Analyzing 2022-2026 data...")
        data = search_tool.run(search_query="software engineer labor market trends 2022-2026 hiring statistics")
        return ask_groq(f"Provide a neutral summary of 2022-2026 software engineering hiring facts: {data}")

    # 2. Sociologist: Engineer Mindset Analysis - Open Source, GitHub, and Career Values
    def analyze_engineer_mindset(self):
        print("▶️ Sociologist: Analyzing dev community mindset...")
        data = search_tool.run(search_query="software engineer career mindset shift open source github trends 2022-2026")
        return ask_groq(f"Analyze engineer career values and community sentiment based on these insights: {data}")

    # 3. Consultant: Recruitment Economics Analysis - Cost and Friction of Hiring Tools
    def analyze_recruitment_economics(self):
        print("▶️ Consultant: Analyzing recruitment tool market...")
        data = search_tool.run(search_query="recruitment tool pricing 2026 HR hiring frustration alternative recruiting methods")
        return ask_groq(f"Analyze the costs and process friction of standard corporate hiring tools: {data}")

    @start()
    async def parallel_execution(self):
        print("🚀 Starting parallel research...")
        results = await asyncio.gather(
            asyncio.to_thread(self.gather_market_facts),
            asyncio.to_thread(self.analyze_engineer_mindset),
            asyncio.to_thread(self.analyze_recruitment_economics)
        )
        return results

    @listen(parallel_execution)
    def synthesize_report(self, results):
        print("▶️ Synthesizer: Building the 'Evidence-Solution' Case...")
        facts, mindset, economics = results
        
        final_prompt = f"""
You are the Lead Analyst. Construct a rigorous evidence-based case for a software recruitment platform that uses GitHub contribution data as its primary screening mechanism.

Analyze the three independent inputs to answer these three specific questions:
1. The Resume Gap: Based on the insights provided (Sociological/Recruitment Economics), is the traditional resume-based hiring process objectively failing to identify top-tier talent in 2026? Why or why not? Be critical and evidence-focused.
2. The GitHub Evidence: Cite specific trends from the provided Data (Market Facts) that show how well GitHub-centric screening (proof-of-work) correlates with actual job performance.
3. The Solution Fit: Explicitly explain whether a 'GitHub-contribution-based system' solves the specific friction points (cost, inefficiency, mismatch) mentioned in the recruitment economics data.

Input Data:
- Market/Tech Trends: {facts}
- Engineer Mindset: {mindset}
- Economic Pain Points: {economics}

Construct this as a 'Proof of Necessity' document. Be professional, skeptical of traditional methods, and evidence-focused.
"""
        return ask_groq(final_prompt)

if __name__ == "__main__":
    flow = ResearchFlow()
    result = flow.kickoff() 
    
    with open("evidence.txt", "w", encoding="utf-8") as f:
        f.write(str(result))