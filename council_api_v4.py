from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import asyncio
from playwright.async_api import async_playwright
import time
import json
from pathlib import Path
from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
import threading

app = Flask(__name__)
CORS(app)

# =============================================================================
# AGENT CONFIGURATION
# =============================================================================

ALL_AGENTS = {
    "Analyst": {
        "url": "https://www.genspark.ai/agents?id=59557c0c-1493-4814-8de1-b304a02665ba",
        "icon": "🔬",
        "name": "The Analyst",
        "expertise": "Evidence-based analysis, data interpretation, systematic reasoning"
    },
    "Strategist": {
        "url": "https://www.genspark.ai/agents?id=ec8b3f1d-80cc-4d1e-af97-a29c09038c5b",
        "icon": "♟️",
        "name": "The Strategist",
        "expertise": "Strategic planning, execution roadmaps, scenario analysis"
    },
    "DevilsAdvocate": {
        "url": "https://www.genspark.ai/agents?id=fa0f916e-2555-406d-85c8-883723568885",
        "icon": "⚔️",
        "name": "The Devil's Advocate",
        "expertise": "Risk assessment, challenge assumptions, failure mode analysis"
    },
    "Creative": {
        "url": "https://www.genspark.ai/agents?id=59704dd9-9275-4e1a-816a-387d39614dc0",
        "icon": "🎨",
        "name": "The Creative",
        "expertise": "Unconventional solutions, innovation, lateral thinking"
    },
    "FinancialAnalyst": {
        "url": "https://www.genspark.ai/agents?id=04d0e973-94e4-433f-ba6e-ea7a320279fa",
        "icon": "💰",
        "name": "The Financial Analyst",
        "expertise": "Financial modeling, projections, investment analysis, unit economics"
    },
    "Synthesiser": {
        "url": "https://www.genspark.ai/agents?id=ba6db65e-743e-4728-8f70-8bfdc7c18056",
        "icon": "⚖️",
        "name": "The Synthesiser",
        "expertise": "Integration, unified recommendations, decision frameworks"
    }
}

COUNCIL_PRESETS = {
    "full": ["Analyst", "Strategist", "DevilsAdvocate", "Creative", "FinancialAnalyst"],
    "core": ["Analyst", "Strategist", "DevilsAdvocate", "Creative"],
    "strategic": ["Strategist", "DevilsAdvocate", "FinancialAnalyst"],
    "financial": ["Analyst", "FinancialAnalyst", "DevilsAdvocate"],
    "creative": ["Creative", "Strategist", "DevilsAdvocate"],
    "quick": ["Analyst", "Strategist"]
}

# Session storage
active_sessions = {}
session_counter = int(time.time())

# =============================================================================
# DOCUMENT GENERATION
# =============================================================================

def create_word_document(session_id, question, responses, synthesis, doc_type="full"):
    """Create Word document with council results"""
    doc = Document()
    
    # Title page
    title = doc.add_heading('AI COUNCIL DELIBERATION', 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    doc.add_paragraph()
    doc.add_paragraph(f"Session ID: {session_id}")
    doc.add_paragraph(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    doc.add_paragraph()
    
    # Question
    doc.add_heading('QUESTION', 1)
    doc.add_paragraph(question)
    doc.add_paragraph()
    
    if doc_type == "executive":
        # Executive Summary - clean synthesis only
        doc.add_heading('EXECUTIVE SUMMARY', 1)
        # Remove advisor mentions
        clean_synthesis = synthesis
        for agent_name in ["ANALYST", "STRATEGIST", "DEVIL'S ADVOCATE", "CREATIVE", "FINANCIAL ANALYST"]:
            clean_synthesis = clean_synthesis.replace(f"**{agent_name}:**", "")
            clean_synthesis = clean_synthesis.replace(f"{agent_name}:", "")
        doc.add_paragraph(clean_synthesis)
    else:
        # Full Report - synthesis first, then perspectives
        doc.add_heading('FINAL SYNTHESIS', 1)
        doc.add_paragraph(synthesis)
        doc.add_paragraph()
        
        doc.add_heading('COUNCIL PERSPECTIVES', 1)
        for advisor, response in responses.items():
            agent_info = ALL_AGENTS.get(advisor, {})
            doc.add_heading(f"{agent_info.get('icon', '')} {agent_info.get('name', advisor)}", 2)
            doc.add_paragraph(f"Expertise: {agent_info.get('expertise', 'N/A')}")
            doc.add_paragraph(response)
            doc.add_paragraph()
    
    # Save
    filename = f"AI_Council_{'Executive' if doc_type == 'executive' else 'Full'}_{session_id}.docx"
    filepath = Path.home() / "Desktop" / "AI_Council" / filename
    doc.save(str(filepath))
    
    return str(filepath)

# =============================================================================
# PLAYWRIGHT AUTOMATION
# =============================================================================

async def consult_advisor(page, advisor_name, question):
    """Consult a single advisor"""
    agent_url = ALL_AGENTS[advisor_name]["url"]
    agent_name = ALL_AGENTS[advisor_name]["name"]
    
    print(f"\n📞 Consulting {agent_name}...")
    
    try:
        await page.goto(agent_url, timeout=30000)
        await page.wait_for_load_state("networkidle", timeout=30000)
        
        # Try to submit question
selectors = [
    'textarea[name="query"]',
    'textarea.search-input',
    'textarea[placeholder*="Ask anything"]',
    'textarea[placeholder*="Ask"]',
    'textarea[placeholder*="Type"]',
    'input[type="text"]',
    '[contenteditable="true"]'
]
        
        submitted = False
        for selector in selectors:
            try:
                input_field = await page.wait_for_selector(selector, timeout=5000)
                if input_field:
                    await input_field.click()
                    await input_field.fill(question)
                    await page.keyboard.press("Enter")
                    submitted = True
                    break
            except:
                continue
        
        if not submitted:
            print(f"⚠️  Could not auto-submit to {agent_name}")
            return "[Manual input required]"
        
        # Wait for response (3 minutes)
        print(f"⏳ Waiting for {agent_name} response...")
        await asyncio.sleep(180)
        
        # Extract response
        body_text = await page.evaluate("document.body.innerText")
        lines = [line.strip() for line in body_text.split('\n') if len(line.strip()) > 50]
        response = '\n'.join(lines[-20:])
        
        print(f"✅ {agent_name} response captured ({len(response)} chars)")
        return response
        
    except Exception as e:
        print(f"❌ Error consulting {agent_name}: {str(e)}")
        return f"[Error: {str(e)}]"

async def run_council_session(session_id, question, context, selected_advisors):
    """Run the complete council session"""
    
    print(f"\n{'='*80}")
    print(f"🏛️  STARTING COUNCIL SESSION {session_id}")
    print(f"{'='*80}")
    
    active_sessions[session_id]["status"] = "in_progress"
    active_sessions[session_id]["progress"] = "Initializing browser..."
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )
        
        context_obj = await browser.new_context()
        
        # Phase 1: Consult advisors in parallel
        active_sessions[session_id]["progress"] = "Consulting council members..."
        
        tasks = []
        for advisor in selected_advisors:
            page = await context_obj.new_page()
            tasks.append(consult_advisor(page, advisor, question))
        
        responses = await asyncio.gather(*tasks)
        
        # Store responses
        advisor_responses = {}
        for i, advisor in enumerate(selected_advisors):
            advisor_responses[advisor] = responses[i]
        
        active_sessions[session_id]["responses"] = advisor_responses
        
        # Phase 2: Synthesis
        active_sessions[session_id]["progress"] = "Synthesizing perspectives..."
        
        synthesis_page = await context_obj.new_page()
        synthesis_prompt = f"""
CONTEXT: {question}

{context if context else ''}

PERSPECTIVES:
"""
        for advisor, response in advisor_responses.items():
            agent_name = ALL_AGENTS[advisor]["name"]
            synthesis_prompt += f"\n**{agent_name.upper()}:**\n{response}\n"
        
        synthesis_prompt += "\n\nPlease synthesize these perspectives into a unified strategic recommendation."
        
        # Submit to Synthesiser
        try:
            await synthesis_page.goto(ALL_AGENTS["Synthesiser"]["url"], timeout=30000)
            await synthesis_page.wait_for_load_state("networkidle", timeout=30000)
            
            # Try to submit
            selectors = [
                'textarea[placeholder*="Ask"]',
                'textarea[placeholder*="Type"]',
                'input[type="text"]',
                '[contenteditable="true"]'
            ]
            
            for selector in selectors:
                try:
                    input_field = await synthesis_page.wait_for_selector(selector, timeout=5000)
                    if input_field:
                        await input_field.click()
                        await input_field.fill(synthesis_prompt)
                        await synthesis_page.keyboard.press("Enter")
                        break
                except:
                    continue
            
            # Wait for synthesis
            await asyncio.sleep(180)
            
            # Extract synthesis
            body_text = await synthesis_page.evaluate("document.body.innerText")
            lines = [line.strip() for line in body_text.split('\n') if len(line.strip()) > 50]
            synthesis = '\n'.join(lines[-30:])
            
        except Exception as e:
            synthesis = f"[Synthesis error: {str(e)}]"
        
        active_sessions[session_id]["synthesis"] = synthesis
        
        await browser.close()
        
        # Generate documents
        active_sessions[session_id]["progress"] = "Generating documents..."
        
        full_doc = create_word_document(session_id, question, advisor_responses, synthesis, "full")
        exec_doc = create_word_document(session_id, question, advisor_responses, synthesis, "executive")
        
        active_sessions[session_id]["full_report_path"] = full_doc
        active_sessions[session_id]["executive_report_path"] = exec_doc
        active_sessions[session_id]["status"] = "complete"
        active_sessions[session_id]["progress"] = "Complete!"
        
        print(f"\n✅ COUNCIL SESSION {session_id} COMPLETE!")

# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "agents": len(ALL_AGENTS), "version": "4.0"})

@app.route('/api/council/start', methods=['POST'])
def start_council():
    global session_counter
    
    data = request.json
    question = data.get('question')
    context = data.get('context', '')
    preset = data.get('preset', 'core')
    custom_advisors = data.get('advisors', [])
    
    if not question:
        return jsonify({"error": "Question required"}), 400
    
    # Determine advisors
    if custom_advisors:
        selected_advisors = custom_advisors
    else:
        selected_advisors = COUNCIL_PRESETS.get(preset, COUNCIL_PRESETS['core'])
    
    # Create session
    session_counter += 1
    session_id = str(session_counter)
    
    active_sessions[session_id] = {
        "question": question,
        "context": context,
        "selected_advisors": selected_advisors,
        "status": "started",
        "progress": "Starting...",
        "responses": {},
        "synthesis": "",
        "timestamp": time.time()
    }
    
    # Run in background
    def run_async():
        asyncio.run(run_council_session(session_id, question, context, selected_advisors))
    
    thread = threading.Thread(target=run_async)
    thread.start()
    
    return jsonify({
        "session_id": session_id,
        "status": "started",
        "advisors": [ALL_AGENTS[a]["name"] for a in selected_advisors]
    })

@app.route('/api/council/status/<session_id>', methods=['GET'])
def get_status(session_id):
    session = active_sessions.get(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    
    return jsonify({
        "status": session["status"],
        "progress": session["progress"],
        "advisors": session["selected_advisors"]
    })

@app.route('/api/council/download/full/<session_id>', methods=['GET'])
def download_full(session_id):
    session = active_sessions.get(session_id)
    if not session or session["status"] != "complete":
        return jsonify({"error": "Report not ready"}), 404
    
    filepath = session.get("full_report_path")
    if not filepath or not Path(filepath).exists():
        return jsonify({"error": "File not found"}), 404
    
    return send_file(filepath, as_attachment=True)

@app.route('/api/council/download/executive/<session_id>', methods=['GET'])
def download_executive(session_id):
    session = active_sessions.get(session_id)
    if not session or session["status"] != "complete":
        return jsonify({"error": "Report not ready"}), 404
    
    filepath = session.get("executive_report_path")
    if not filepath or not Path(filepath).exists():
        return jsonify({"error": "File not found"}), 404
    
    return send_file(filepath, as_attachment=True)

# =============================================================================
# MAIN
# =============================================================================

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    
    print("\n" + "="*80)
    print("🏛️  AI COUNCIL API v4.0")
    print("="*80)
    print(f"\n✅ Server: http://0.0.0.0:{port}")
    print("✅ Financial Analyst: ACTIVE")
    print("✅ 6 Council Members Ready")
    print("\nPress Ctrl+C to stop\n")
    
    app.run(host='0.0.0.0', port=port, debug=False)
