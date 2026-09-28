import os
import time
from playwright.sync_api import sync_playwright

def run_recording():
    output_dir = os.path.abspath("recordings")
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"Starting Playwright video capture in {output_dir}...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--window-size=1920,1080"
            ]
        )
        
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            record_video_dir=output_dir,
            record_video_size={"width": 1920, "height": 1080}
        )
        
        page = context.new_page()
        
        def smooth_sleep(seconds):
            time.sleep(seconds)
            
        print("Navigating to http://127.0.0.1:8000...")
        page.goto("http://127.0.0.1:8000", wait_until="networkidle")
        smooth_sleep(2)
        
        # 1. Login View
        print("Scene 1: Login View...")
        page.wait_for_selector(".u[data-role='CTRL']")
        smooth_sleep(1.5)
        page.click(".u[data-role='CTRL']")
        smooth_sleep(1.5)
        page.click("#btnLogin")
        smooth_sleep(3)
        
        # 2. Operations Dashboard
        print("Scene 2: Operations Dashboard...")
        page.wait_for_selector("#appView")
        smooth_sleep(4)
        
        # Hover over top elements
        page.hover(".logo")
        smooth_sleep(1)
        page.hover("#topZone")
        smooth_sleep(1)
        page.hover("#backendBadge")
        smooth_sleep(2)
        
        # Scroll gently through dashboard
        page.mouse.wheel(0, 300)
        smooth_sleep(3)
        page.mouse.wheel(0, -300)
        smooth_sleep(2)
        
        # 3. Network Map
        print("Scene 3: Network Map...")
        page.click(".navItem[data-view='network']")
        smooth_sleep(5)
        
        # 4. Live Trains
        print("Scene 4: Live Trains...")
        page.click(".navItem[data-view='trains']")
        smooth_sleep(4)
        page.mouse.wheel(0, 250)
        smooth_sleep(3)
        page.mouse.wheel(0, -250)
        smooth_sleep(1)
        
        # 5. Asset Health
        print("Scene 5: Asset Health...")
        page.click(".navItem[data-view='assets']")
        smooth_sleep(4)
        page.mouse.wheel(0, 300)
        smooth_sleep(3)
        page.mouse.wheel(0, -300)
        smooth_sleep(1)
        
        # 6. Maintenance Queue & Ingestion
        print("Scene 6: Multi-Modal Ingestion & LAYA Triage...")
        page.click(".navItem[data-view='requests']")
        smooth_sleep(3)
        
        # Open New Request
        page.click("button:has-text('+ Raise Request'), button:has-text('+ New Request')")
        smooth_sleep(2)
        
        # Show Voice Mode Tab
        print("Showcasing Local Voice Whisper Mode...")
        page.click(".inputModeBtn[data-mode='voice']")
        smooth_sleep(3)
        
        # Back to Preset Mode
        page.click(".inputModeBtn[data-mode='preset']")
        smooth_sleep(1.5)
        
        # Select TVC-QLN Section
        if page.is_visible("#mSection"):
            page.select_option("#mSection", "TVC-QLN")
            smooth_sleep(1)
        
        # Select Priority High
        if page.is_visible("#mPriority"):
            page.select_option("#mPriority", "HIGH")
            smooth_sleep(1)
            
        # Ensure Auto-evaluate with LAYA is checked
        if page.is_visible("#mAuto"):
            if not page.is_checked("#mAuto"):
                page.check("#mAuto")
            smooth_sleep(1)
            
        # Submit Request
        print("Submitting Maintenance Request...")
        page.click("#mSubmit")
        smooth_sleep(4)
        
        # 7. Block Planner & OR-Tools Optimization
        print("Scene 7: Block Planner & OR-Tools Optimization...")
        # Check if Plan Block button is in the requests table
        plan_btn = page.query_selector("button:has-text('Plan Block')")
        if plan_btn:
            plan_btn.click()
            smooth_sleep(3)
        else:
            page.click(".navItem[data-view='planner']")
            smooth_sleep(3)
            
        # Select Google OR-Tools CP-SAT
        if page.is_visible("#solverSelect"):
            page.select_option("#solverSelect", "ortools")
            smooth_sleep(1.5)
            
        # Click Calculate Feasible Candidates
        if page.is_visible("#btnCalculateCandidates"):
            page.click("#btnCalculateCandidates")
            print("Calculating candidates with OR-Tools CP-SAT...")
            smooth_sleep(5)
            
        # Select first candidate
        cand_cards = page.query_selector_all(".candCard")
        if cand_cards:
            cand_cards[0].click()
            smooth_sleep(3)
            
        # 8. Human Section Controller Verification (G&SR 15.06)
        print("Scene 8: Human Section Controller Statutory Verification...")
        page.mouse.wheel(0, 450)
        smooth_sleep(2)
        
        # Complete Statutory Checklist
        if page.is_visible("#chkHeadway"):
            page.check("#chkHeadway")
            smooth_sleep(0.8)
        if page.is_visible("#chkExpress"):
            page.check("#chkExpress")
            smooth_sleep(0.8)
        if page.is_visible("#chkPower"):
            page.check("#chkPower")
            smooth_sleep(0.8)
        # Check fourth box if present
        chk_emergency = page.query_selector("input[onchange*='emergency_corridor']")
        if chk_emergency:
            chk_emergency.check()
            smooth_sleep(0.8)
            
        # Approve Block Possession
        btn_approve = page.query_selector("#btnApproveBlock")
        if btn_approve and not btn_approve.is_disabled():
            btn_approve.click()
            print("Block possession approved by Section Controller!")
            smooth_sleep(4)
            
        page.mouse.wheel(0, -450)
        smooth_sleep(2)
        
        # 9. Blocks Schedule (Gantt Chart)
        print("Scene 9: Blocks Schedule & Gantt Chart...")
        page.click(".navItem[data-view='schedule']")
        smooth_sleep(5)
        page.mouse.wheel(0, 250)
        smooth_sleep(2)
        page.mouse.wheel(0, -250)
        smooth_sleep(1)
        
        # 10. What-If Disruption Simulator & Dynamic Reoptimization
        print("Scene 10: What-If Disruption Simulator...")
        page.click(".navItem[data-view='whatif']")
        smooth_sleep(3)
        
        # Select Jan Shatabdi 12076 & +60 min delay
        if page.is_visible("#simTrain"):
            # Select Jan Shatabdi if in options
            options = page.query_selector_all("#simTrain option")
            for opt in options:
                val = opt.get_attribute("value")
                if "12076" in val or "Jan" in (opt.inner_text() or ""):
                    page.select_option("#simTrain", val)
                    break
            smooth_sleep(1)
            
        if page.is_visible("#simDelay"):
            page.select_option("#simDelay", "60")
            smooth_sleep(1)
            
        if page.is_visible("#simType"):
            page.select_option("#simType", "SIGNAL_MALFUNCTION")
            smooth_sleep(1)
            
        if page.is_visible("#simSection"):
            page.select_option("#simSection", "TVC-QLN")
            smooth_sleep(1)
            
        # Run Simulation
        print("Running Disruption Simulation...")
        page.click("#btnRunSimulation")
        smooth_sleep(5)
        
        page.mouse.wheel(0, 350)
        smooth_sleep(4)
        
        # Check for reoptimization action button if present
        reopt_btn = page.query_selector("button:has-text('Approve Reoptimized'), button:has-text('Reoptimize')")
        if reopt_btn:
            reopt_btn.click()
            smooth_sleep(4)
            
        page.mouse.wheel(0, -350)
        smooth_sleep(2)
        
        # 11. Tamper-Evident Audit Trail & Metrics
        print("Scene 11: Tamper-Evident Audit Trail...")
        page.click(".navItem[data-view='audit']")
        smooth_sleep(5)
        page.mouse.wheel(0, 300)
        smooth_sleep(3)
        page.mouse.wheel(0, -300)
        smooth_sleep(2)
        
        # 12. Return to Dashboard (Conclusion)
        print("Scene 12: Concluding Dashboard View...")
        page.click(".navItem[data-view='dashboard']")
        smooth_sleep(5)
        
        print("Closing context to finalize video recording...")
        context.close()
        browser.close()
        
    print("Recording completed successfully!")
    
    # List recorded files
    files = os.listdir(output_dir)
    print("Recorded files in recordings folder:", files)

if __name__ == "__main__":
    run_recording()
