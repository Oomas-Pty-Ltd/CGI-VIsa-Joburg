#!/usr/bin/env python3
"""
Multi-language Chat Testing for Seva Setu Bot
Tests Hindi, English, Afrikaans, Zulu responses
"""

import requests
import json
import time

API_URL = "https://seva-bridge-1.preview.emergentagent.com/api"

def test_multilang_chat():
    """Test multi-language chat functionality"""
    
    test_messages = [
        {
            "message": "Hello, I need help with passport application",
            "language": "en",
            "expected_lang": "English"
        },
        {
            "message": "नमस्ते, मुझे पासपोर्ट के लिए मदद चाहिए",
            "language": "hi", 
            "expected_lang": "Hindi (Devanagari)"
        },
        {
            "message": "Hallo, ek het hulp nodig met my paspoort aansoek",
            "language": "af",
            "expected_lang": "Afrikaans"
        },
        {
            "message": "Sawubona, ngidinga usizo ngokufaka isicelo sephasipoti",
            "language": "zu",
            "expected_lang": "Zulu"
        }
    ]
    
    print("🌍 Testing Multi-Language Chat Functionality")
    print("=" * 60)
    
    for i, test in enumerate(test_messages, 1):
        print(f"\n{i}. Testing {test['expected_lang']}:")
        print(f"   Input: {test['message']}")
        
        try:
            response = requests.post(
                f"{API_URL}/consular/chat",
                json={
                    "message": test['message'],
                    "user_id": "test_user",
                    "enable_voice": True,
                    "language": test['language']
                },
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                print(f"   ✅ Response received (Session: {data.get('session_id', 'N/A')[:8]}...)")
                print(f"   📝 Bot Response: {data.get('response', 'No response')[:100]}...")
                print(f"   🎵 Audio Generated: {'Yes' if data.get('audio_base64') else 'No'}")
                print(f"   📊 Step: {data.get('step', 'N/A')}")
                
                # Wait a bit for AI processing
                time.sleep(2)
            else:
                print(f"   ❌ Failed: HTTP {response.status_code}")
                print(f"   Error: {response.text}")
                
        except Exception as e:
            print(f"   ❌ Exception: {str(e)}")
    
    print(f"\n{'='*60}")
    print("✅ Multi-language testing completed!")

if __name__ == "__main__":
    test_multilang_chat()