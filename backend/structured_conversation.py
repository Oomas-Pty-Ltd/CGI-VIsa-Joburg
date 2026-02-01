"""
Structured Conversation Handler
Implements consent-first, one-question-at-a-time bot flow
"""
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from database import get_database
from admin_config import get_admin_config, get_service_links, get_document_requirements, log_exception
from application_tracking import create_application, get_user_applications
import uuid

# Conversation states
CONVERSATION_STATES = {
    "greeting": "Initial greeting - awaiting consent",
    "consent_pending": "Waiting for consent",
    "service_selection": "Selecting service",
    "service_details": "Gathering service details",
    "document_check": "Checking document requirements",
    "form_filling": "Filling form step by step",
    "review": "Reviewing information",
    "ready_to_apply": "Ready to apply",
    "post_submission": "Post submission - appointment booking",
    "appointment_booking": "Booking appointment",
    "completed": "Conversation completed"
}


async def get_or_create_conversation(session_id: str, user_name: str = None) -> Dict:
    """Get or create a conversation session"""
    db = await get_database()
    
    conversation = await db.conversations.find_one({"session_id": session_id}, {"_id": 0})
    
    if not conversation:
        conversation = {
            "session_id": session_id,
            "state": "greeting",
            "consent_given": False,
            "consent_timestamp": None,
            "user_name": user_name,
            "profile_id": None,
            "selected_service": None,
            "service_details": {},
            "current_step": 0,
            "total_steps": 0,
            "collected_data": {},
            "documents_submitted": [],
            "documents_required": [],
            "documents_missing": [],
            "application_id": None,
            "history": [],
            "messages": [],
            "last_service": None,  # For "Last time you did X" feature
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        await db.conversations.insert_one(conversation)
    
    return conversation


async def update_conversation(session_id: str, updates: Dict) -> Dict:
    """Update conversation state"""
    db = await get_database()
    
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.conversations.update_one(
        {"session_id": session_id},
        {"$set": updates}
    )
    
    return await get_or_create_conversation(session_id)


async def add_message_to_conversation(session_id: str, role: str, content: str):
    """Add a message to conversation history"""
    db = await get_database()
    
    message = {
        "id": str(uuid.uuid4()),
        "role": role,
        "content": content,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    await db.conversations.update_one(
        {"session_id": session_id},
        {
            "$push": {"messages": message},
            "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}
        }
    )


async def get_greeting_message(conversation: Dict, config: Dict) -> Dict:
    """Generate greeting message with consent request"""
    bot_config = config.get("bot_config", {})
    greeting = bot_config.get("greeting_message", 
        "Hi! 👋 I'm Seva Setu Bot, your consular services assistant. I'll guide you step-by-step for Visa, Passport, PCC, or other services.\n\nDo I have your consent to proceed and assist you? (YES/NO)")
    
    # Check if returning user
    if conversation.get("last_service"):
        last_service = conversation["last_service"]
        greeting = f"Welcome back! 👋 Last time you inquired about **{last_service}**.\n\nWould you like to continue with the same service, or choose a different one?\n\nFirst, do I have your consent to proceed? (YES/NO)"
    
    # Personalize if name is known
    user_name = conversation.get("user_name")
    if user_name:
        greeting = greeting.replace("Hi!", f"Hi {user_name}!")
        greeting = greeting.replace("Welcome back!", f"Welcome back, {user_name}!")
    
    return {
        "response": greeting,
        "state": "consent_pending",
        "waiting_for": "consent",
        "progress": {"current": 0, "total": 5, "percent": 0}
    }


async def get_service_selection_message(conversation: Dict, config: Dict) -> Dict:
    """Generate service selection message"""
    top_services = await get_service_links(top_only=True)
    
    service_list = "\n".join([
        f"**{i+1}.** {svc['name']}" for i, svc in enumerate(top_services)
    ])
    
    user_name = conversation.get("user_name", "")
    name_prefix = f"{user_name}, w" if user_name else "W"
    
    response = f"""✅ Thank you for your consent!

{name_prefix}hich service do you need help with today?

{service_list}
**6.** Others (more options)

📝 Reply with the **number** or type the service name."""
    
    return {
        "response": response,
        "state": "service_selection",
        "waiting_for": "service_choice",
        "progress": {"current": 1, "total": 5, "percent": 20}
    }


async def get_other_services_message(conversation: Dict, config: Dict) -> Dict:
    """Generate other services message"""
    all_services = await get_service_links(top_only=False)
    
    # Skip first 5 (top services)
    other_services = all_services[5:] if len(all_services) > 5 else []
    
    if not other_services:
        return {
            "response": "No additional services available. Please choose from the main list or describe what you need.",
            "state": "service_selection",
            "waiting_for": "service_choice"
        }
    
    service_list = "\n".join([
        f"**{i+6}.** {svc['name']}" for i, svc in enumerate(other_services)
    ])
    
    response = f"""📋 **Additional Services:**

{service_list}

Or type your specific requirement and I'll guide you.

📝 Reply with the **number** or describe your need."""
    
    return {
        "response": response,
        "state": "service_selection",
        "waiting_for": "service_choice",
        "progress": {"current": 1, "total": 5, "percent": 20}
    }


async def get_service_confirmation_message(
    conversation: Dict, 
    service: Dict,
    config: Dict
) -> Dict:
    """Confirm selected service and ask first detail question"""
    user_name = conversation.get("user_name", "")
    name_mention = f", {user_name}" if user_name else ""
    
    response = f"""✅ **Service Selected:** {service['name']}

Great choice{name_mention}! Let me guide you through this step-by-step.

**Step 1/5: Basic Information**

Is this application for yourself or someone else (family member/dependent)?

1️⃣ For myself
2️⃣ For a family member
3️⃣ For my child (minor)

📝 Reply with the number."""
    
    return {
        "response": response,
        "state": "service_details",
        "waiting_for": "applicant_type",
        "progress": {"current": 2, "total": 5, "percent": 40}
    }


async def get_document_checklist_message(
    conversation: Dict,
    service_id: str,
    config: Dict
) -> Dict:
    """Show document requirements checklist"""
    requirements = await get_document_requirements(service_id)
    
    required_docs = requirements.get("required", [])
    optional_docs = requirements.get("optional", [])
    
    required_list = "\n".join([
        f"☐ {doc['description']} {'🔴 (Original Required)' if doc.get('original_required') else ''}"
        for doc in required_docs
    ])
    
    optional_list = "\n".join([
        f"☐ {doc['description']} (Optional)"
        for doc in optional_docs
    ]) if optional_docs else "None"
    
    service_name = conversation.get("selected_service", {}).get("name", "this service")
    user_name = conversation.get("user_name", "")
    name_mention = f"{user_name}, here" if user_name else "Here"
    
    response = f"""📋 **Document Checklist for {service_name}**

{name_mention} are the documents you'll need:

**Required Documents:**
{required_list}

**Optional Documents:**
{optional_list}

⚠️ **Important:** Please bring ORIGINAL documents at the time of submission.

Do you have all the required documents ready?

1️⃣ Yes, I have all documents
2️⃣ No, I'm missing some documents
3️⃣ I need to upload documents now

📝 Reply with the number."""
    
    return {
        "response": response,
        "state": "document_check",
        "waiting_for": "document_status",
        "progress": {"current": 3, "total": 5, "percent": 60},
        "documents_required": [doc["type"] for doc in required_docs]
    }


async def get_missing_documents_message(
    conversation: Dict,
    missing_docs: List[str]
) -> Dict:
    """Show which documents are missing"""
    doc_list = "\n".join([f"❌ {doc}" for doc in missing_docs])
    
    response = f"""⚠️ **Missing Documents Detected:**

{doc_list}

You'll need these documents to complete your application.

**Options:**
1️⃣ Upload the missing documents now
2️⃣ Continue anyway (you can upload later)
3️⃣ Cancel and come back when ready

📝 Reply with the number."""
    
    return {
        "response": response,
        "state": "document_check",
        "waiting_for": "missing_doc_action",
        "progress": {"current": 3, "total": 5, "percent": 60}
    }


async def get_ready_to_apply_message(
    conversation: Dict,
    config: Dict
) -> Dict:
    """Final confirmation before providing apply link"""
    service = conversation.get("selected_service", {})
    collected_data = conversation.get("collected_data", {})
    
    # Build summary
    summary_items = []
    for key, value in collected_data.items():
        if value:
            label = key.replace("_", " ").title()
            summary_items.append(f"• **{label}:** {value}")
    
    summary = "\n".join(summary_items) if summary_items else "• Basic information collected"
    
    user_name = conversation.get("user_name", "")
    name_mention = f"{user_name}, you're" if user_name else "You're"
    
    response = f"""🎉 **{name_mention} almost ready!**

**Service:** {service.get('name', 'Selected Service')}

**Your Information:**
{summary}

**Next Steps:**
1. Click the link below to open the application form
2. Fill in the form with your details
3. Submit the form
4. Return here to book your appointment

⚠️ **Remember:** Bring ORIGINAL documents when you visit.

**Are you ready to proceed?**

1️⃣ Yes, give me the apply link
2️⃣ No, I need to make changes
3️⃣ Save and continue later

📝 Reply with the number."""
    
    return {
        "response": response,
        "state": "ready_to_apply",
        "waiting_for": "apply_confirmation",
        "progress": {"current": 4, "total": 5, "percent": 80}
    }


async def get_apply_link_message(
    conversation: Dict,
    config: Dict
) -> Dict:
    """Provide the apply link"""
    service = conversation.get("selected_service", {})
    service_url = service.get("url", "https://vfs.matchlessmfs.com/")
    service_name = service.get("name", "your application")
    
    user_name = conversation.get("user_name", "")
    name_mention = f"{user_name}, here's" if user_name else "Here's"
    
    response = f"""✅ **{name_mention} your application link:**

🔗 **Apply Now:** [{service_name}]({service_url})

**Instructions:**
1. Click the link above
2. Complete the application form
3. Print the form for verification
4. Sign the form manually
5. Return here after submission

⚠️ **Important:** 
• Verify all information before submitting
• Keep your reference number safe
• Do NOT close this chat - you'll need to book an appointment

**After you've submitted the form, reply:**
✅ "DONE" - to proceed with appointment booking
⏸️ "PAUSE" - to continue later

Did you complete the form? (DONE/PAUSE)"""
    
    return {
        "response": response,
        "state": "post_submission",
        "waiting_for": "submission_status",
        "progress": {"current": 4, "total": 5, "percent": 85}
    }


async def get_appointment_booking_message(
    conversation: Dict,
    config: Dict
) -> Dict:
    """Guide to appointment booking"""
    service_links = config.get("service_links", {})
    appointment_url = service_links.get("appointment_booking", {}).get("url", "https://vfs.matchlessmfs.com/appointment")
    
    user_name = conversation.get("user_name", "")
    name_mention = f"Great job, {user_name}!" if user_name else "Great job!"
    
    response = f"""🎊 **{name_mention} Form submitted successfully!**

**Step 5/5: Book Your Appointment**

Now let's book your appointment to submit your documents.

🔗 **Book Appointment:** [{appointment_url}]({appointment_url})

**Appointment Process:**
1. Click the link above
2. Select your preferred date and time
3. Note down your appointment reference number
4. Bring all ORIGINAL documents on appointment day

**After booking, share your appointment details:**
• Date: 
• Time:
• Reference Number:

Or reply "BOOKED" when done.

Need help with appointment booking? Reply "HELP"."""
    
    return {
        "response": response,
        "state": "appointment_booking",
        "waiting_for": "appointment_status",
        "progress": {"current": 5, "total": 5, "percent": 95}
    }


async def get_completion_message(
    conversation: Dict,
    config: Dict
) -> Dict:
    """Completion message"""
    user_name = conversation.get("user_name", "")
    name_mention = f"Congratulations, {user_name}!" if user_name else "Congratulations!"
    
    service_links = config.get("service_links", {})
    tracking_url = service_links.get("status_tracking", {}).get("url", "https://vfs.matchlessmfs.com/track")
    
    response = f"""🎉 **{name_mention} All done!**

✅ Service Selected
✅ Documents Verified  
✅ Application Submitted
✅ Appointment Booked

**What's Next:**
1. Visit on your appointment date with all ORIGINAL documents
2. Pay the applicable fees
3. Collect your receipt/acknowledgment

**Track Your Application:**
🔗 [{tracking_url}]({tracking_url})

**Need more help?**
• Reply "NEW" - Start a new service
• Reply "STATUS" - Check application status
• Reply "HELP" - Get assistance

Thank you for using Seva Setu Bot! 🙏"""
    
    return {
        "response": response,
        "state": "completed",
        "waiting_for": "new_action",
        "progress": {"current": 5, "total": 5, "percent": 100}
    }


async def process_user_input(
    session_id: str,
    user_message: str,
    profile_id: str = None,
    user_name: str = None
) -> Dict:
    """Main function to process user input and return structured response"""
    
    # Get conversation state
    conversation = await get_or_create_conversation(session_id, user_name)
    config = await get_admin_config()
    
    # Update user name if provided
    if user_name and not conversation.get("user_name"):
        await update_conversation(session_id, {"user_name": user_name})
        conversation["user_name"] = user_name
    
    if profile_id and not conversation.get("profile_id"):
        await update_conversation(session_id, {"profile_id": profile_id})
        conversation["profile_id"] = profile_id
    
    # Log user message
    await add_message_to_conversation(session_id, "user", user_message)
    
    state = conversation.get("state", "greeting")
    user_input = user_message.strip().lower()
    
    # Handle universal commands
    if user_input in ["stop", "pause", "cancel"]:
        response = await handle_pause(conversation, config)
    elif user_input in ["help", "?"]:
        response = await handle_help(conversation, config)
    elif user_input in ["new", "start", "restart"]:
        await update_conversation(session_id, {"state": "greeting", "consent_given": False})
        response = await get_greeting_message(conversation, config)
    elif user_input == "status":
        response = await handle_status_check(conversation, config)
    else:
        # Process based on current state
        if state == "greeting":
            response = await get_greeting_message(conversation, config)
        
        elif state == "consent_pending":
            response = await handle_consent(session_id, user_input, conversation, config)
        
        elif state == "service_selection":
            response = await handle_service_selection(session_id, user_input, conversation, config)
        
        elif state == "service_details":
            response = await handle_service_details(session_id, user_input, conversation, config)
        
        elif state == "document_check":
            response = await handle_document_check(session_id, user_input, conversation, config)
        
        elif state == "ready_to_apply":
            response = await handle_apply_confirmation(session_id, user_input, conversation, config)
        
        elif state == "post_submission":
            response = await handle_post_submission(session_id, user_input, conversation, config)
        
        elif state == "appointment_booking":
            response = await handle_appointment_booking(session_id, user_input, conversation, config)
        
        elif state == "completed":
            response = await handle_completed_state(session_id, user_input, conversation, config)
        
        else:
            response = await get_greeting_message(conversation, config)
    
    # Log bot response
    await add_message_to_conversation(session_id, "assistant", response["response"])
    
    # Update state if changed
    if response.get("state") != state:
        await update_conversation(session_id, {"state": response["state"]})
    
    return response


async def handle_consent(session_id: str, user_input: str, conversation: Dict, config: Dict) -> Dict:
    """Handle consent response"""
    if user_input in ["yes", "y", "ok", "okay", "sure", "agree", "i agree"]:
        await update_conversation(session_id, {
            "consent_given": True,
            "consent_timestamp": datetime.now(timezone.utc).isoformat()
        })
        return await get_service_selection_message(conversation, config)
    
    elif user_input in ["no", "n", "nope", "disagree"]:
        return {
            "response": "No problem! I respect your decision. If you change your mind, just say 'START' to begin again.\n\nHave a great day! 🙏",
            "state": "greeting",
            "waiting_for": "consent",
            "progress": {"current": 0, "total": 5, "percent": 0}
        }
    
    else:
        return {
            "response": "I need your consent to proceed. Please reply:\n\n**YES** - to continue with assistance\n**NO** - to decline\n\nDo I have your consent? (YES/NO)",
            "state": "consent_pending",
            "waiting_for": "consent",
            "progress": {"current": 0, "total": 5, "percent": 0}
        }


async def handle_service_selection(session_id: str, user_input: str, conversation: Dict, config: Dict) -> Dict:
    """Handle service selection"""
    all_services = await get_service_links(top_only=False)
    
    # Check for "others"
    if user_input in ["6", "others", "other", "more"]:
        return await get_other_services_message(conversation, config)
    
    # Try to match by number
    try:
        choice = int(user_input)
        if 1 <= choice <= len(all_services):
            selected_service = all_services[choice - 1]
            await update_conversation(session_id, {
                "selected_service": selected_service,
                "last_service": selected_service["name"]
            })
            return await get_service_confirmation_message(conversation, selected_service, config)
    except ValueError:
        pass
    
    # Try to match by name
    for service in all_services:
        if user_input in service["name"].lower() or service["name"].lower() in user_input:
            await update_conversation(session_id, {
                "selected_service": service,
                "last_service": service["name"]
            })
            return await get_service_confirmation_message(conversation, service, config)
    
    # Not recognized
    return {
        "response": f"I didn't quite catch that. Please select a service by:\n\n• Entering the **number** (1-{len(all_services)})\n• Or typing the **service name**\n\nWhich service do you need?",
        "state": "service_selection",
        "waiting_for": "service_choice",
        "progress": {"current": 1, "total": 5, "percent": 20}
    }


async def handle_service_details(session_id: str, user_input: str, conversation: Dict, config: Dict) -> Dict:
    """Handle service detail questions"""
    waiting_for = conversation.get("waiting_for", "")
    collected_data = conversation.get("collected_data", {})
    
    if waiting_for == "applicant_type":
        applicant_types = {
            "1": "self", "myself": "self", "me": "self",
            "2": "family", "family member": "family",
            "3": "child", "minor": "child"
        }
        
        applicant_type = applicant_types.get(user_input, None)
        if applicant_type:
            collected_data["applicant_type"] = applicant_type
            await update_conversation(session_id, {
                "collected_data": collected_data,
                "waiting_for": "name_confirmation"
            })
            
            user_name = conversation.get("user_name", "")
            if user_name and applicant_type == "self":
                return {
                    "response": f"**Step 2/5: Confirm Your Details**\n\nI have your name as: **{user_name}**\n\nIs this correct?\n\n1️⃣ Yes, that's correct\n2️⃣ No, let me provide the correct name\n\n📝 Reply with the number.",
                    "state": "service_details",
                    "waiting_for": "name_confirmation",
                    "progress": {"current": 2, "total": 5, "percent": 45}
                }
            else:
                return {
                    "response": "**Step 2/5: Applicant Name**\n\nPlease provide the full name of the applicant (as per passport):\n\n📝 Type the full name:",
                    "state": "service_details",
                    "waiting_for": "applicant_name",
                    "progress": {"current": 2, "total": 5, "percent": 45}
                }
        else:
            return {
                "response": "Please select:\n\n1️⃣ For myself\n2️⃣ For a family member\n3️⃣ For my child (minor)\n\n📝 Reply with the number.",
                "state": "service_details",
                "waiting_for": "applicant_type",
                "progress": {"current": 2, "total": 5, "percent": 40}
            }
    
    elif waiting_for == "name_confirmation":
        if user_input in ["1", "yes", "correct"]:
            collected_data["applicant_name"] = conversation.get("user_name")
            await update_conversation(session_id, {"collected_data": collected_data})
            service_id = conversation.get("selected_service", {}).get("id", "")
            return await get_document_checklist_message(conversation, service_id, config)
        else:
            return {
                "response": "Please provide the correct full name (as per passport):\n\n📝 Type the full name:",
                "state": "service_details",
                "waiting_for": "applicant_name",
                "progress": {"current": 2, "total": 5, "percent": 45}
            }
    
    elif waiting_for == "applicant_name":
        if len(user_input) > 2:
            collected_data["applicant_name"] = user_input.title()  # Use user_input, not user_message
            await update_conversation(session_id, {"collected_data": collected_data})
            service_id = conversation.get("selected_service", {}).get("id", "")
            return await get_document_checklist_message(conversation, service_id, config)
        else:
            return {
                "response": "Please provide a valid full name:\n\n📝 Type the full name:",
                "state": "service_details",
                "waiting_for": "applicant_name",
                "progress": {"current": 2, "total": 5, "percent": 45}
            }
    
    # Default
    service_id = conversation.get("selected_service", {}).get("id", "")
    return await get_document_checklist_message(conversation, service_id, config)


async def handle_document_check(session_id: str, user_input: str, conversation: Dict, config: Dict) -> Dict:
    """Handle document check responses"""
    if user_input in ["1", "yes"]:
        return await get_ready_to_apply_message(conversation, config)
    
    elif user_input in ["2", "no", "missing"]:
        return await get_missing_documents_message(
            conversation,
            conversation.get("documents_required", ["Required documents"])
        )
    
    elif user_input in ["3", "upload"]:
        return {
            "response": "📤 **Upload Documents**\n\nPlease use the **upload button** (📄) below to upload your documents.\n\nSupported formats: JPG, PNG, PDF\n\nAfter uploading, I'll extract the information and verify your documents.\n\n📝 Upload your documents or reply 'DONE' when finished.",
            "state": "document_check",
            "waiting_for": "document_upload",
            "progress": {"current": 3, "total": 5, "percent": 65}
        }
    
    elif user_input == "done":
        return await get_ready_to_apply_message(conversation, config)
    
    else:
        return {
            "response": "Please select:\n\n1️⃣ Yes, I have all documents\n2️⃣ No, I'm missing some\n3️⃣ Upload documents now\n\n📝 Reply with the number.",
            "state": "document_check",
            "waiting_for": "document_status",
            "progress": {"current": 3, "total": 5, "percent": 60}
        }


async def handle_apply_confirmation(session_id: str, user_input: str, conversation: Dict, config: Dict) -> Dict:
    """Handle apply confirmation"""
    if user_input in ["1", "yes", "ready"]:
        return await get_apply_link_message(conversation, config)
    
    elif user_input in ["2", "no", "change", "edit"]:
        return {
            "response": "What would you like to change?\n\n1️⃣ Service type\n2️⃣ Applicant details\n3️⃣ Documents\n4️⃣ Start over\n\n📝 Reply with the number.",
            "state": "ready_to_apply",
            "waiting_for": "edit_choice",
            "progress": {"current": 4, "total": 5, "percent": 75}
        }
    
    elif user_input in ["3", "save", "later"]:
        return {
            "response": "✅ **Progress Saved!**\n\nYour information has been saved. You can continue anytime by:\n\n• Coming back to this chat\n• Saying 'CONTINUE' to resume\n\nSee you soon! 🙏",
            "state": "ready_to_apply",
            "waiting_for": "resume",
            "progress": {"current": 4, "total": 5, "percent": 80}
        }
    
    else:
        return await get_ready_to_apply_message(conversation, config)


async def handle_post_submission(session_id: str, user_input: str, conversation: Dict, config: Dict) -> Dict:
    """Handle post submission flow"""
    if user_input in ["done", "submitted", "yes", "complete"]:
        return await get_appointment_booking_message(conversation, config)
    
    elif user_input in ["pause", "later"]:
        return {
            "response": "✅ **Got it!** Take your time filling the form.\n\nWhen you've submitted, come back and say 'DONE' to proceed with appointment booking.\n\nNeed help? Say 'HELP' anytime.",
            "state": "post_submission",
            "waiting_for": "submission_status",
            "progress": {"current": 4, "total": 5, "percent": 85}
        }
    
    else:
        return {
            "response": "Have you submitted the application form?\n\n✅ **DONE** - Yes, I've submitted\n⏸️ **PAUSE** - Not yet, I'll continue later\n\n📝 Reply DONE or PAUSE.",
            "state": "post_submission",
            "waiting_for": "submission_status",
            "progress": {"current": 4, "total": 5, "percent": 85}
        }


async def handle_appointment_booking(session_id: str, user_input: str, conversation: Dict, config: Dict) -> Dict:
    """Handle appointment booking flow"""
    if user_input in ["booked", "done", "yes"]:
        return await get_completion_message(conversation, config)
    
    elif user_input == "help":
        service_links = config.get("service_links", {})
        appointment_url = service_links.get("appointment_booking", {}).get("url", "https://vfs.matchlessmfs.com/appointment")
        
        return {
            "response": f"""📅 **Appointment Booking Help**

**Steps to book:**
1. Go to: {appointment_url}
2. Select your service type
3. Choose available date and time
4. Enter your application reference
5. Confirm booking

**Tips:**
• Book early - slots fill up fast
• Morning slots are usually available
• Keep your reference number handy

🔗 **Book Now:** [{appointment_url}]({appointment_url})

Reply 'BOOKED' when you're done!""",
            "state": "appointment_booking",
            "waiting_for": "appointment_status",
            "progress": {"current": 5, "total": 5, "percent": 95}
        }
    
    else:
        return {
            "response": "Have you booked your appointment?\n\n✅ **BOOKED** - Yes, appointment confirmed\n❓ **HELP** - I need help booking\n\n📝 Reply BOOKED or HELP.",
            "state": "appointment_booking",
            "waiting_for": "appointment_status",
            "progress": {"current": 5, "total": 5, "percent": 95}
        }


async def handle_completed_state(session_id: str, user_input: str, conversation: Dict, config: Dict) -> Dict:
    """Handle completed state actions"""
    if user_input in ["new", "start", "another"]:
        await update_conversation(session_id, {
            "state": "consent_pending",
            "selected_service": None,
            "collected_data": {},
            "current_step": 0
        })
        conversation["consent_given"] = True  # Already consented
        return await get_service_selection_message(conversation, config)
    
    elif user_input == "status":
        return await handle_status_check(conversation, config)
    
    else:
        return await get_completion_message(conversation, config)


async def handle_pause(conversation: Dict, config: Dict) -> Dict:
    """Handle pause/stop command"""
    return {
        "response": "⏸️ **Conversation Paused**\n\nYour progress has been saved. You can resume anytime by saying 'CONTINUE'.\n\nHave a great day! 🙏",
        "state": conversation.get("state", "greeting"),
        "waiting_for": "resume",
        "progress": conversation.get("progress", {"current": 0, "total": 5, "percent": 0})
    }


async def handle_help(conversation: Dict, config: Dict) -> Dict:
    """Handle help command"""
    state = conversation.get("state", "greeting")
    
    help_text = """❓ **Help Menu**

**Commands you can use:**
• **NEW** - Start a new service request
• **STATUS** - Check application status
• **STOP** - Pause and save progress
• **CONTINUE** - Resume from where you left

**Current Progress:**
"""
    
    progress = conversation.get("progress", {"current": 0, "total": 5, "percent": 0})
    help_text += f"Step {progress['current']}/{progress['total']} ({progress['percent']}%)\n\n"
    help_text += "How can I help you?"
    
    return {
        "response": help_text,
        "state": state,
        "waiting_for": conversation.get("waiting_for", ""),
        "progress": progress
    }


async def handle_status_check(conversation: Dict, config: Dict) -> Dict:
    """Handle status check"""
    service_links = config.get("service_links", {})
    tracking_url = service_links.get("status_tracking", {}).get("url", "https://vfs.matchlessmfs.com/track")
    
    return {
        "response": f"""📊 **Check Application Status**

To track your application:

🔗 **Track Here:** [{tracking_url}]({tracking_url})

You'll need your:
• Application reference number
• Date of birth
• Passport number

Need help with something else? Reply 'NEW' to start a new request.""",
        "state": conversation.get("state", "completed"),
        "waiting_for": "new_action",
        "progress": {"current": 5, "total": 5, "percent": 100}
    }
