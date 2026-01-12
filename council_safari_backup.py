import asyncio
from playwright.async_api import async_playwright
import sys
import json
from pathlib import Path

# Your GenSpark Council URLs
AGENTS = {
    "Analyst": "https://www.genspark.ai/agents?id=59557c0c-1493-4814-8de1-b304a02665ba",
    "Strategist": "https://www.genspark.ai/agents?id=ec8b3f1d-80cc-4d1e-af97-a29c09038c5b",
    "DevilsAdvocate": "https://www.genspark.ai/agents?id=fa0f916e-2555-406d-85c8-883723568885",
    "Creative": "https://www.genspark.ai/agents?id=59704dd9-9275-4e1a-816a-387d39614dc0",
    "Synthesiser": "https://www.genspark.ai/agents?id=ba6db65e-743e-4728-8f70-8bfdc7c18056"
}

# Session storage for login persistence
SESSION_FILE = Path.home() / ".genspark_session.json"

async def save_session(context):
    """Save login session for future runs"""
    storage = await context.storage_state()
    SESSION_FILE.write_text(json.dumps(storage))
    print("   💾 Session saved!")

async def run_council(question):
    print("\n" + "="*80)
    print("🏛️  COUNCIL SESSION INITIATED")
    print("="*80)
    print(f"\n📋 Question: {question}\n")
    
    async with async_playwright() as p:
        # ✅ SAFARI (WebKit) - This is the key line!
        print("🌐 Launching Safari...")
        browser = await p.webkit.launch(headless=False)
        
        # Load saved session if exists
        if SESSION_FILE.exists():
            context = await browser.new_context(storage_state=str(SESSION_FILE))
            print("   ✅ Using saved login")
        else:
            context = await browser.new_context()
            print("   ⚠️  First run - you'll need to log in")
        
        # Check login status
        print("\n🔐 Checking login...")
        test_page = await context.new_page()
        await test_page.goto(AGENTS["Analyst"], timeout=30000)
        await asyncio.sleep(3)
        
        page_content = await test_page.content()
        if "sign in" in page_content.lower() or "log in" in page_content.lower():
            print("\n" + "="*60)
            print("⚠️  PLEASE LOG IN")
            print("="*60)
            print("Log into GenSpark in the Safari window.")
            print("Press ENTER after logging in...")
            print("="*60)
            input()
            await save_session(context)
            await test_page.reload()
            await asyncio.sleep(2)
        else:
            print("   ✅ Already logged in!")
        
        await test_page.close()
        
        # Phase 1: Consult advisors
        print("\n" + "-"*80)
        print("PHASE 1: CONSULTING ADVISORS")
        print("-"*80)
        
        responses = {}
        advisors = ["Analyst", "Strategist", "DevilsAdvocate", "Creative"]
        
        for advisor in advisors:
            print(f"\n🔬 {advisor}...")
            page = await context.new_page()
            
            try:
                await page.goto(AGENTS[advisor], timeout=30000)
                await asyncio.sleep(5)
                
                # Try to auto-submit
                print(f"   🔍 Finding input...")
                filled = False
                
                for selector in ['textarea', 'input[type="text"]', '[contenteditable="true"]']:
                    try:
                        element = await page.wait_for_selector(selector, timeout=5000)
                        if element:
                            await element.fill(question)
                            await asyncio.sleep(1)
                            await page.keyboard.press("Enter")
                            print(f"   ✅ Question submitted!")
                            filled = True
                            break
                    except:
                        continue
                
                if not filled:
                    print(f"   ⚠️  Please type manually:")
                    print(f"   \"{question}\"")
                    print(f"   Press ENTER after response...")
                    input()
                else:
                    print(f"   ⏳ Waiting 60 seconds...")
                    await asyncio.sleep(60)
                
                # Extract response
                print(f"   📥 Capturing response...")
                body_text = await page.evaluate('() => document.body.innerText')
                
                # Get substantial content
                lines = [l for l in body_text.split('\n') if len(l) > 50]
                response = '\n'.join(lines[-20:])
                
                if len(response) < 100:
                    print(f"   ⚠️  Manual review needed")
                    input("   Press ENTER to continue...")
                    response = "[See browser tab]"
                
                responses[advisor] = response
                print(f"   ✅ Captured ({len(response)} chars)")
                
            except Exception as e:
                print(f"   ⚠️  Error: {e}")
                responses[advisor] = f"[Error: {e}]"
        
        # Phase 2: Synthesis
        print("\n" + "-"*80)
        print("PHASE 2: SYNTHESIS")
        print("-"*80)
        
        synthesis_prompt = f"""**CONTEXT:**
Question: "{question}"

**ANALYST:**
{responses.get('Analyst', '[No response]')}

**STRATEGIST:**
{responses.get('Strategist', '[No response]')}

**DEVIL'S ADVOCATE:**
{responses.get('DevilsAdvocate', '[No response]')}

**CREATIVE:**
{responses.get('Creative', '[No response]')}

---

**YOUR TASK:**
Synthesize these perspectives into a unified recommendation.
"""
        
        page = await context.new_page()
        await page.goto(AGENTS["Synthesiser"], timeout=30000)
        await asyncio.sleep(3)
        
        print("\n" + "="*80)
        print("📋 COPY THIS PROMPT:")
        print("="*80)
        print(synthesis_prompt)
        print("="*80)
        print("\n⏸️  Paste into Synthesiser, then press ENTER...")
        input()
        
        print("\n✅ COUNCIL SESSION COMPLETE!")
        input("Press ENTER to close browser...")
        await browser.close()

def main():
    if len(sys.argv) < 2:
        print("\nUsage: python3 council.py 'Your question'")
        sys.exit(1)
    
    question = " ".join(sys.argv[1:])
    asyncio.run(run_council(question))

if __name__ == "__main__":
    main()
