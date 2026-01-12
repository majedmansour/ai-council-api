import asyncio
from playwright.async_api import async_playwright
import sys
from pathlib import Path
import threading

AGENTS = {
    "Analyst": "https://www.genspark.ai/agents?id=59557c0c-1493-4814-8de1-b304a02665ba",
    "Strategist": "https://www.genspark.ai/agents?id=ec8b3f1d-80cc-4d1e-af97-a29c09038c5b",
    "DevilsAdvocate": "https://www.genspark.ai/agents?id=fa0f916e-2555-406d-85c8-883723568885",
    "Creative": "https://www.genspark.ai/agents?id=59704dd9-9275-4e1a-816a-387d39614dc0",
    "Synthesiser": "https://www.genspark.ai/agents?id=ba6db65e-743e-4728-8f70-8bfdc7c18056"
}

def interruptible_wait(seconds, message="Waiting"):
    """Wait for specified seconds, but allow ENTER to skip"""
    print(f"\n⏳ {message} ({seconds//60} minutes)")
    print("💡 Press ENTER anytime if finished early, or wait for timer...")
    
    user_interrupted = [False]
    
    def wait_for_input():
        input()
        user_interrupted[0] = True
    
    # Start input listener thread
    input_thread = threading.Thread(target=wait_for_input, daemon=True)
    input_thread.start()
    
    # Count down with progress updates
    elapsed = 0
    while elapsed < seconds:
        if user_interrupted[0]:
            print("   ✅ Continuing early (user pressed ENTER)")
            return True  # User chose to continue
        
        await_time = min(30, seconds - elapsed)  # Check every 30 seconds
        import time
        time.sleep(await_time)
        elapsed += await_time
        
        if elapsed < seconds and not user_interrupted[0]:
            remaining = seconds - elapsed
            print(f"   ⏱️  {elapsed//60}m {elapsed%60}s elapsed ({remaining//60}m {remaining%60}s remaining)")
    
    print("   ⏰ Timer complete!")
    return False  # Timer finished naturally

async def consult_advisor(context, advisor_name, question):
    """Consult a single advisor (runs in parallel with others)"""
    print(f"[{advisor_name}] Opening...")
    page = await context.new_page()
    
    try:
        await page.goto(AGENTS[advisor_name], timeout=30000)
        await asyncio.sleep(5)
        
        # Try to submit question
        filled = False
        for selector in ['textarea', 'input[type="text"]', '[contenteditable="true"]']:
            try:
                element = await page.wait_for_selector(selector, timeout=5000)
                if element and await element.is_visible():
                    await element.fill(question)
                    await asyncio.sleep(1)
                    await page.keyboard.press("Enter")
                    print(f"[{advisor_name}] ✅ Question submitted!")
                    filled = True
                    break
            except:
                continue
        
        if not filled:
            print(f"[{advisor_name}] ⚠️  Could not auto-submit. Please type manually in the browser.")
            return page, "[Manual - see browser tab]"
        
        return page, None
        
    except Exception as e:
        print(f"[{advisor_name}] ❌ Error: {e}")
        return page, f"[Error: {e}]"

async def collect_response(page, advisor_name):
    """Collect response from an advisor page"""
    try:
        body_text = await page.evaluate('() => document.body.innerText')
        lines = [l for l in body_text.split('\n') if len(l) > 50]
        response = '\n'.join(lines[-30:])
        
        if len(response) > 100:
            print(f"[{advisor_name}] ✅ Response captured ({len(response)} characters)")
            return response
        else:
            print(f"[{advisor_name}] ⚠️  Response seems short - see browser tab")
            return "[See browser tab for full response]"
    except Exception as e:
        print(f"[{advisor_name}] ❌ Error collecting response: {e}")
        return "[Error collecting response]"

async def run_council(question):
    print("\n" + "="*80)
    print("🏛️  AI COUNCIL SESSION - PARALLEL MODE")
    print("="*80)
    print(f"\n📋 Question: {question}\n")
    
    async with async_playwright() as p:
        print("🌐 Launching Chrome...")
        
        user_data_dir = Path.home() / ".playwright_chrome_data"
        user_data_dir.mkdir(exist_ok=True)
        
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=False,
            args=['--disable-blink-features=AutomationControlled']
        )
        
        # Check login
        print("\n🔐 Checking login...")
        test_page = await context.new_page()
        await test_page.goto(AGENTS["Analyst"], timeout=30000)
        await asyncio.sleep(3)
        
        page_content = await test_page.content()
        if "sign in" in page_content.lower():
            print("\n" + "="*60)
            print("⚠️  PLEASE LOG INTO GENSPARK")
            print("="*60)
            print("Press ENTER after logging in...")
            input()
            await test_page.reload()
            await asyncio.sleep(2)
        else:
            print("   ✅ Already logged in!")
        
        await test_page.close()
        
        # PHASE 1: PARALLEL CONSULTATION
        print("\n" + "="*80)
        print("PHASE 1: CONSULTING ALL 4 ADVISORS IN PARALLEL")
        print("="*80)
        
        advisors = ["Analyst", "Strategist", "DevilsAdvocate", "Creative"]
        
        # Launch all advisors at once
        print("\n🚀 Opening all advisors simultaneously...")
        tasks = [consult_advisor(context, advisor, question) for advisor in advisors]
        results = await asyncio.gather(*tasks)
        
        # Store pages and early errors
        advisor_pages = {}
        responses = {}
        
        for advisor, (page, error) in zip(advisors, results):
            advisor_pages[advisor] = page
            if error:
                responses[advisor] = error
        
        # Wait 4 minutes (interruptible)
        interruptible_wait(240, "Waiting for all 4 advisors to respond")
        
        # Ask if more time needed
        print("\n" + "="*60)
        print("⏸️  CHECK BROWSER TABS")
        print("="*60)
        print("Have all advisors finished responding?")
        print("Press ENTER to continue, or type 'wait' for 2 more minutes...")
        user_input = input().strip().lower()
        
        if user_input == 'wait':
            interruptible_wait(120, "Waiting 2 more minutes")
            
            print("\nNeed even more time?")
            print("Press ENTER to continue, or type 'wait' for 1 more minute...")
            user_input = input().strip().lower()
            
            if user_input == 'wait':
                interruptible_wait(60, "Waiting 1 more minute")
        
        # Collect all responses
        print("\n📥 Collecting all responses...")
        for advisor in advisors:
            if advisor not in responses:
                responses[advisor] = await collect_response(advisor_pages[advisor], advisor)
        
        # PHASE 2: SYNTHESIS
        print("\n" + "="*80)
        print("PHASE 2: SYNTHESIS")
        print("="*80)
        
        synthesis_prompt = f"""**CONTEXT:**
I have consulted the council on this question: "{question}"

**THE ANALYST'S PERSPECTIVE:**
{responses.get('Analyst', '[No response]')}

**THE STRATEGIST'S PERSPECTIVE:**
{responses.get('Strategist', '[No response]')}

**THE DEVIL'S ADVOCATE'S PERSPECTIVE:**
{responses.get('DevilsAdvocate', '[No response]')}

**THE CREATIVE'S PERSPECTIVE:**
{responses.get('Creative', '[No response]')}

---

**YOUR TASK:**
Synthesize these four perspectives into a unified recommendation using your standard framework:
1. Perspective Acknowledgment
2. Agreement Mapping
3. Disagreement Analysis
4. Integration Logic
5. Unified Recommendation
6. Decision Framework & Next Steps
"""
        
        print("\n⚖️  Opening The Synthesiser...")
        synth_page = await context.new_page()
        await synth_page.goto(AGENTS["Synthesiser"], timeout=30000)
        await asyncio.sleep(5)
        
        # Try auto-paste
        print("🤖 Attempting to auto-paste synthesis prompt...")
        auto_pasted = False
        
        for selector in ['textarea', 'input[type="text"]', '[contenteditable="true"]']:
            try:
                element = await synth_page.wait_for_selector(selector, timeout=5000)
                if element and await element.is_visible():
                    await element.click()
                    await asyncio.sleep(1)
                    await element.fill(synthesis_prompt)
                    await asyncio.sleep(2)
                    await synth_page.keyboard.press("Enter")
                    print("   ✅ AUTO-PASTE SUCCESSFUL!")
                    auto_pasted = True
                    break
            except:
                continue
        
        # Fallback: Manual paste
        if not auto_pasted:
            print("\n⚠️  Auto-paste failed. MANUAL MODE:")
            print("\n" + "="*80)
            print("📋 SYNTHESIS PROMPT (COPY THIS):")
            print("="*80)
            print(synthesis_prompt)
            print("="*80)
            print("\nPaste into Synthesiser manually, then press ENTER here...")
            input()
        
        # Wait for synthesis (3 minutes, interruptible)
        interruptible_wait(180, "Waiting for synthesis")
        
        print("\n" + "="*60)
        print("⏸️  CHECK THE SYNTHESISER TAB")
        print("="*60)
        print("Has The Synthesiser finished?")
        print("Press ENTER to continue, or type 'wait' for 2 more minutes...")
        user_input = input().strip().lower()
        
        if user_input == 'wait':
            interruptible_wait(120, "Waiting 2 more minutes for synthesis")
        
        # Final message
        print("\n" + "="*80)
        print("✅ COUNCIL SESSION COMPLETE!")
        print("="*80)
        print("\n📊 RESULTS:")
        print("   • All 4 advisor perspectives collected")
        print("   • Final synthesis generated by The Synthesiser")
        print("   • All tabs remain open for your review")
        print("\n💡 Review The Synthesiser tab for the final recommendation.")
        print("\nPress ENTER to close browser...")
        input()
        
        await context.close()

def main():
    if len(sys.argv) < 2:
        print("\n❌ Error: No question provided")
        print("\nUsage: python3 council_chrome.py 'Your question here'")
        print("\nExample:")
        print("   python3 council_chrome.py 'What is the best agricultural project for Oman?'")
        sys.exit(1)
    
    question = " ".join(sys.argv[1:])
    asyncio.run(run_council(question))

if __name__ == "__main__":
    main()
