#!/usr/bin/env python3
"""Apply intent classification changes to api.py"""
import re

# Read api.py
with open('src/api.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add QueryIntent to imports
content = content.replace(
    'QuestionRequest, QuestionResponse, UploadResponse,',
    'QuestionRequest, QuestionResponse, QueryIntent, UploadResponse,'
)

# Update the ask_question endpoint
old_pattern = r'answer, sources = await loop\.run_in_executor\([^)]+\)'
new_code = '''result = await loop.run_in_executor(
            None, 
            assistant.ask_question, 
            payload.query,
            payload.document_filters,
            conversation_context,
            None  # advanced_filters - will be None for regular requests
        )
        
        # Unpack result (answer, sources, intent_info)
        if len(result) == 3:
            answer, sources, intent_info = result
        else:
            # Backward compatibility: if only 2 values returned
            answer, sources = result
            intent_info = {"intent": "factual", "confidence": 0.5}'''

content = re.sub(old_pattern, new_code, content, flags=re.DOTALL)

# Update logger line
content = content.replace(
    'logger.info(f"Response generated ({len(answer)} chars) with {len(sources)} sources in {elapsed_time:.2f}s")',
    'logger.info(f"Response generated ({len(answer)} chars) with {len(sources)} sources, intent: {intent_info.get(\'intent\', \'unknown\')} in {elapsed_time:.2f}s")'
)

# Update return statement
old_return = 'return {"response": answer, "sources": sources}'
new_return = '''# Build response with intent information
        intent_obj = QueryIntent(
            intent=intent_info.get("intent", "factual"),
            confidence=intent_info.get("confidence", 0.5)
        ) if intent_info else None
        
        return {"response": answer, "sources": sources, "intent": intent_obj}'''

content = content.replace(old_return, new_return, 1)

# Write back
with open('src/api.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("✓ Applied intent classification changes to api.py")

