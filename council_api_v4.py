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

# Agent definitions
ALL_AGENTS = {
    "Analyst": {
        "url": "https://www.genspark.ai/agents?id=59557c0c-1493-4814-8de1-b304a02665ba",
        "role": "Data-Driven Analysis",
        "icon": "📊"
    },
    "Strategist": {
        "url": "https://www.genspark.ai/agents?id=ec8b3f1d-80cc-4d1e-af97-a29c09038c5b",
        "role": "Strategic Planning",
        "icon": "🎯"
    },
    "DevilsAdvocate": {
        "url": "https://www.genspark.ai/agents?id=fa0f916e-2555-406d-85c8-883723568885",
        "role": "Critical Analysis",
        "icon": "⚠️"
    },
    "Creative": {
        "url": "https://www.genspark.ai/agents?id=59704dd9-9275-4e1a-816a-387d39614dc0",
        "role": "Innovation & Ideas",
        "icon": "💡"
    },
    "FinancialAnalyst": {
        "url": "https://www.genspark.ai/agents?id=04d0e973-94e4-433f-ba6e-ea7a320279fa",
        "role": "Financial Perspective",
        "icon": "💰"
    },
    "Synthesiser": {
        "url": "https://www.genspark.ai/agents?id=ba6db65e-743e-4728-8f70-8bfdc7c18056",
        "role": "Integration & Recommendations",
        "icon": "🔄"
    }
}

COUNCIL_PRESETS = {
    "full": ["Analyst", "Strategist", "DevilsAdvocate", "Creative", "FinancialAnalyst", "Synthesiser"],
    "core": ["Analyst", "Strategist", "DevilsAdvocate", "Creative"],
    "strategic": ["Strategist", "Analyst", "DevilsAdvocate"],
    "financial": ["FinancialAnalyst", "Analyst", "Strategist"],
    "creative": ["Creative", "Strategist", "Analyst"],
    "quick": ["Analyst", "Strategist"]
}

sessions = {}

async def consult_agent(agent_name, agent_info, question, context=""):
    full_question = f"{question}\n\nContext: {context}" if context else question
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        try:
            print(f"🔍 Consulting {agent_name}...")
            await page.goto(agent_info['url'], timeout=60000, wait_until='networkidle')
            
            selectors = [
                'textarea.active',
                'textarea.search-input',
                'textarea[name="query"]',
                'textarea[placeholder*="Ask"]',
                'input[type="text"]',
                '[contenteditable="true"]'
            ]
            
            input_field = None
            for selector in selectors:
                try:
                    input_field = await page.wait_for_selector(selector, timeout=10000, state='visible')
                    if input_field:
                        print(f"✅ Found input field with selector: {selector}")
                        break
                except:
                    continue
            
            if not input_field:
                return f"[Error: Could not find input field for {agent_name}]"
            
            await input_field.fill(full_question)
            await input_field.press('Enter')
            print(f"✅ Submitted to {agent_name}")
            
            print(f"⏳ Waiting for {agent_name} response (180s timeout)...")
            await page.wait_for_timeout(180000)
            
            response_selectors = [
                '.response-content',
                '.message-content',
                '[role="article"]',
                '.chat-message',
                'div[class*="response"]',
                'div[class*="answer"]'
            ]
            
            response_text = ""
            for selector in response_selectors:
                try:
                    elements = await page.query_selector_all(selector)
                    if elements and len(elements) > 0:
                        last_element = elements[-1]
                        response_text = await last_element.inner_text()
                        if response_text and len(response_text) > 50:
                            break
                except:
                    continue
            
            if not response_text or len(response_text) < 50:
                page_text = await page.inner_text('body')
                lines = page_text.split('\n')
                response_text = '\n'.join([line for line in lines if len(line) > 30])[-2000:]
            
            print(f"✅ Captured response from {agent_name}: {response_text[:100]}...")
            
            await browser.close()
            return response_text if response_text else f"[No response captured from {agent_name}]"
            
        except Exception as e:
            await browser.close()
            print(f"❌ Error consulting {agent_name}: {str(e)}")
            return f"[Error: {str(e)}]"

def generate_word_docs(session_id, question, context, responses):
    # Executive Summary
    exec_doc = Document()
    exec_doc.add_heading('AI COUNCIL - EXECUTIVE SUMMARY', 0)
    exec_doc.add_paragraph(f'Session: {session_id}')
    exec_doc.add_paragraph(f'Question: {question}')
    if context:
        exec_doc.add_paragraph(f'Context: {context}')
    
    exec_doc.add_heading('RECOMMENDATION', 1)
    if 'Synthesiser' in responses:
        exec_doc.add_paragraph(responses['Synthesiser'])
    else:
        exec_doc.add_paragraph('Synthesis not available.')
    
    exec_path = f'/tmp/Council_Executive_{session_id}.docx'
    exec_doc.save(exec_path)
    
    # Full Report
    full_doc = Document()
    full_doc.add_heading('AI COUNCIL DELIBERATION', 0)
    full_doc.add_paragraph(f'Session: {session_id}')
    full_doc.add_paragraph(f'Question: {question}')
    if context:
        full_doc.add_paragraph(f'Context: {context}')
    
    full_doc.add_heading('SYNTHESIS', 1)
    if 'Synthesiser' in responses:
        full_doc.add_paragraph(responses['Synthesiser'])
    else:
        full_doc.add_paragraph('[Synthesis error: No synthesis available]')
    
    full_doc.add_heading('ADVISOR PERSPECTIVES', 1)
    for agent_name, response in responses.items():
        if agent_name != 'Synthesiser':
            full_doc.add_heading(agent_name.replace('DevilsAdvocate', "Devil's Advocate"), 2)
            full_doc.add_paragraph(response)
    
    full_path = f'/tmp/Council_Full_{session_id}.docx'
    full_doc.save(full_path)
    
    return {'executive': exec_path, 'full': full_path}

async def run_council(session_id, question, context, advisors):
    sessions[session_id]['status'] = 'in_progress'
    sessions[session_id]['progress'] = f'Consulting {len(advisors)} council members...'
    
    responses = {}
    for advisor_name in advisors:
        if advisor_name in ALL_AGENTS:
            sessions[session_id]['progress'] = f'Consulting {advisor_name}...'
            response = await consult_agent(advisor_name, ALL_AGENTS[advisor_name], question, context)
            responses[advisor_name] = response
    
    sessions[session_id]['progress'] = 'Generating reports...'
    docs = generate_word_docs(session_id, question, context, responses)
    
    sessions[session_id]['status'] = 'complete'
    sessions[session_id]['responses'] = responses
    sessions[session_id]['docs'] = docs
    sessions[session_id]['progress'] = 'Complete'

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        "status": "ok",
        "agents": len(ALL_AGENTS),
        "version": "4.0"
    })

@app.route('/api/council/start', methods=['POST'])
def start_council():
    data = request.json
    question = data.get('question', '')
    context = data.get('context', '')
    preset = data.get('preset', 'core')
    
    if not question:
        return jsonify({"error": "Question is required"}), 400
    
    advisors = COUNCIL_PRESETS.get(preset, COUNCIL_PRESETS['core'])
    session_id = str(int(time.time()))
    
    sessions[session_id] = {
        "question": question,
        "context": context,
        "advisors": advisors,
        "status": "started",
        "progress": "Initializing...",
        "responses": {},
        "docs": {}
    }
    
    def run_async_council():
        asyncio.run(run_council(session_id, question, context, advisors))
    
    thread = threading.Thread(target=run_async_council, daemon=True)
    thread.start()
    
    return jsonify({
        "session_id": session_id,
        "status": "started",
        "advisors": advisors
    })

@app.route('/api/council/status/<session_id>', methods=['GET'])
def get_status(session_id):
    if session_id not in sessions:
        return jsonify({"error": "Session not found"}), 404
    
    session = sessions[session_id]
    return jsonify({
        "status": session['status'],
        "progress": session['progress']
    })

@app.route('/api/council/download/full/<session_id>', methods=['GET'])
def download_full(session_id):
    if session_id not in sessions:
        return jsonify({"error": "Session not found"}), 404
    
    session = sessions[session_id]
    if session['status'] != 'complete':
        return jsonify({"error": "Council deliberation not complete"}), 400
    
    filepath = session['docs']['full']
    return send_file(filepath, as_attachment=True)

@app.route('/api/council/download/executive/<session_id>', methods=['GET'])
def download_executive(session_id):
    if session_id not in sessions:
        return jsonify({"error": "Session not found"}), 404
    
    session = sessions[session_id]
    if session['status'] != 'complete':
        return jsonify({"error": "Council deliberation not complete"}), 400
    
    filepath = session['docs']['executive']
    return send_file(filepath, as_attachment=True)
