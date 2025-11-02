import asyncio
import json
import traceback
from browser import closeBrowser, wait_for_element
from navigation import post_login_navigation

async def startLogin(page, email, password, record_id=None):
    try:
        email_input = await wait_for_element(page, "#username", 30)
        if not email_input:
            msg = {"status": "FAILED", "recordId": record_id, "error": "Email input not found"}
            print(json.dumps(msg), flush=True)
            return msg

        await email_input.send_keys(email)

        password_input = await wait_for_element(page, "input[type='password']", 30)
        if not password_input:
            msg = {"status": "FAILED", "recordId": record_id, "error": "Password input not found"}
            print(json.dumps(msg), flush=True)
            return msg

        await password_input.send_keys(password)

        login_btn = await wait_for_element(page, "#kc-login", 30)
        if not login_btn:
            msg = {"status": "FAILED", "recordId": record_id, "error": "Login button not found"}
            print(json.dumps(msg), flush=True)
            return msg

        await login_btn.click()
        error_icon = await wait_for_element(page, ".pf-c-alert__icon", timeout=5)
        if error_icon:
            msg = {"status": "NOT_FOUND", "error": "User not found", "recoverable": True}
            print(json.dumps(msg), flush=True)
            return msg

        otp_field = await wait_for_element(page, "#otp, input[type='tel'], input[name='otp'], #emailCode, #verificationCode", 15)
        if otp_field:
            msg = {"status": "OTP_REQUIRED", "recordId": record_id}
            print(json.dumps(msg), flush=True)
            return msg

        dashboard = await wait_for_element(page, "#dashboard", 10)
        if dashboard:
            msg = {"status": "LOGIN_SUCCESS", "recordId": record_id}
            print(json.dumps(msg), flush=True)
            return msg

        msg = {"status": "FAILED", "recordId": record_id, "error": "Unknown login state"}
        print(json.dumps(msg), flush=True)
        return msg

    except Exception as e:
        tb = traceback.format_exc()
        msg = {"status": "FAILED", "recordId": record_id, "error": str(e), "traceback": tb}
        print(json.dumps(msg), flush=True)
        return msg

async def submitOtp(page, otp, record_id=None):
    if not page:
        msg = {"status": "FAILED", "recordId": record_id, "error": "No login session"}
        print(json.dumps(msg), flush=True)
        return msg

    try:
        otp_input = await wait_for_element(page, "#otp, input[type='tel'], input[name='otp'], #emailCode, #verificationCode", 30)
        if not otp_input:
            await closeBrowser()
            msg = {"status": "FAILED", "recordId": record_id, "error": "OTP input not found"}
            print(json.dumps(msg), flush=True)
            return msg

        await otp_input.click()
        await otp_input.send_keys(otp)
        await asyncio.sleep(0.5)

        verify_btn = None
        for sel in [
            "input[name='login'][type='submit']",
            "input[name='login']",
            "button[type='submit']",
            "button[name='login']",
            ".login-button",
            "input[type='submit']"
        ]:
            verify_btn = await wait_for_element(page, sel, timeout=3)
            if verify_btn:
                break

        if not verify_btn:
            await closeBrowser()
            msg = {"status": "FAILED", "recordId": record_id, "error": "Verify button not found"}
            print(json.dumps(msg), flush=True)
            return msg

        await verify_btn.click()
        await asyncio.sleep(3)
        error_message = await wait_for_element(page, "#input-error-otp-code", timeout=1)
        
        # Convert debug prints to JSON messages
        debug_msg = {"type": "DEBUG", "message": "Looking for error message"}
        print(json.dumps(debug_msg), flush=True)
        
        if error_message:
            error_text = error_message.text
            debug_msg = {"type": "DEBUG", "message": f"Error message found: {error_text}"}
            print(json.dumps(debug_msg), flush=True)
            
            msg = {"status": "OTP_FAILED", "message": "Try Again", "recoverable": True}
            print(json.dumps(msg), flush=True)
            return msg

        nav_result = await post_login_navigation(page)
        if nav_result["status"] == "SUCCESS":
            msg = {"status": "SUCCESS", "recordId": record_id}
            print(json.dumps(msg), flush=True)
            return msg

        dashboard = await wait_for_element(page, "#dashboard, .dashboard, .welcome, [class*='success']", 15)
        if dashboard:
            msg = {"status": "SUCCESS", "recordId": record_id, "warning": "Navigation skipped (dashboard found)"}
            print(json.dumps(msg), flush=True)
            return msg

        await closeBrowser()
        msg = {"status": "FAILED", "recordId": record_id, **nav_result}
        print(json.dumps(msg), flush=True)
        return msg

    except Exception as e:
        await closeBrowser()
        tb = traceback.format_exc()
        msg = {"status": "FAILED", "recordId": record_id, "error": str(e), "traceback": tb}
        print(json.dumps(msg), flush=True)
        return msg