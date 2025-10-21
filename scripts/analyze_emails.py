import json
import os

# Load email communications
email_file = r"C:\Users\USER\Documents\projects\virtualoffice\simulation_output\1week_korean_multiproject_20251020_142911\email_communications.json"
with open(email_file, 'r', encoding='utf-8') as f:
    emails = json.load(f)

print(f"Total emails: {len(emails)}")
print(f"\n=== FIRST 10 EMAILS ===\n")

for i, email in enumerate(emails[:10]):
    print(f"\n--- Email {i+1} ---")
    print(f"From: {email.get('from_address', 'N/A')}")
    print(f"To: {email.get('to_addresses', 'N/A')}")
    print(f"CC: {email.get('cc_addresses', [])}")
    print(f"Subject: {email.get('subject', 'N/A')}")
    print(f"Thread ID: {email.get('thread_id', 'N/A')}")
    print(f"In Reply To: {email.get('in_reply_to', 'N/A')}")
    body = email.get('body', '')
    print(f"Body ({len(body)} chars): {body[:200]}...")
    print(f"Word count: {len(body.split())}")
    print(f"Sentence count: {body.count('.')}")

# Statistics
total_words = sum(len(email.get('body', '').split()) for email in emails)
total_sentences = sum(email.get('body', '').count('.') for email in emails)
threaded = sum(1 for email in emails if email.get('thread_id'))
with_cc = sum(1 for email in emails if email.get('cc_addresses'))

print(f"\n=== EMAIL STATISTICS ===")
print(f"Total emails: {len(emails)}")
print(f"Average words per email: {total_words / len(emails):.1f}")
print(f"Average sentences per email: {total_sentences / len(emails):.1f}")
print(f"Emails with thread_id: {threaded} ({threaded/len(emails)*100:.1f}%)")
print(f"Emails with CC: {with_cc} ({with_cc/len(emails)*100:.1f}%)")
