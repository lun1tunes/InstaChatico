# Agent Tools Documentation Guide

## Overview

This document explains how tools are structured for the OpenAI Agents SDK and how the agent interprets them.

## How Agents SDK Parses Tools

According to the Agents SDK documentation:

1. **Tool Name**: Taken from the Python function name (or provided explicitly)
2. **Tool Description**: Extracted from the function's docstring
3. **Parameter Schema**: Automatically created from function arguments
4. **Parameter Descriptions**: Parsed from the docstring's Args section

**Key Insight**: The docstring is the primary way the agent learns about the tool!

## Tool Structure Best Practices

### 1. Comprehensive Docstring

```python
async def tool_function(param1: str, param2: int = 5) -> str:
    """
    Brief one-line summary of what the tool does.

    Detailed explanation of the tool's purpose and behavior.
    Include important warnings, limitations, and special cases.

    USE THIS TOOL WHEN:
    - Clear use case 1
    - Clear use case 2
    - Clear use case 3

    DO NOT USE when:
    - Anti-pattern 1
    - Anti-pattern 2

    Args:
        param1: Detailed description of param1. Include expected format,
               constraints, and examples. Be specific about what this parameter
               controls or affects.
        param2: Detailed description of param2. Explain default behavior if not
               provided. Include valid ranges or options if applicable.

    Returns:
        Clear description of what the function returns, including:
        - Format of the return value
        - Possible variations in output
        - What different return values mean

    Examples:
        Example 1:
        - param1: "example value"
          param2: 10
          Returns: Description of expected output

        Example 2 (edge case):
        - param1: "edge case"
          Returns: How tool handles this case
    """
```

### 2. Why This Matters

**Without proper docstrings:**
```python
async def search(q: str, n: int = 5) -> str:
    """Search products"""
```
❌ Agent doesn't know:
- When to use this tool
- What `q` should contain
- What `n` controls
- What the return format is

**With proper docstrings:**
```python
async def search(query: str, limit: int = 5) -> str:
    """
    Search for products using semantic similarity.

    USE THIS TOOL WHEN: Customer asks about products.
    DO NOT USE for: General business questions.

    Args:
        query: Natural language search (e.g., "apartments", "квартиры")
        limit: Max results to return (default: 5, max: 10)

    Returns:
        Formatted list of products or "not found" message
    """
```
✅ Agent understands:
- Exactly when to use the tool
- What to pass as `query`
- How `limit` affects results
- What to expect in return

## Our Tools Documentation

### 1. embedding_search

**File**: `src/core/agents/tools/embedding_search_tool.py`

**Agent Understanding**:
```
Tool Name: embedding_search

Description:
"Search for products and services using semantic similarity with
automatic filtering of irrelevant results."

Parameters:
- query (required, string):
  "Natural language search query in any language. Be specific for best results."
  Examples: "apartments in center", "квартиры", "premium consulting"

- limit (optional, integer, default=5):
  "Maximum number of high-confidence results to return. Max is 10.
  Only results above 70% similarity threshold are returned."

- category (optional, string):
  "Optional filter to search only in specific category.
  Use this to narrow search when you know the category."
  Examples: "Недвижимость", "Услуги"

Returns:
"Formatted string with one of three outcomes:
1. HIGH-CONFIDENCE RESULTS with product details
2. NO RELEVANT PRODUCTS FOUND (not in catalog)
3. DATABASE EMPTY (suggest alternative contact)"

Use Cases (from docstring):
✓ Customer asks about products: "Do you have apartments?"
✓ Price/availability questions: "How much for consultation?"
✓ Feature searches: "квартиры в центре"

Don't Use For:
✗ Business hours, contact info, location
✗ Non-product questions
```

**Critical Information Agent Learns**:

1. **OOD Handling**: "If tool returns NO RELEVANT PRODUCTS FOUND, politely inform customer it's unavailable"
2. **Threshold**: "Automatically filters below 70% similarity"
3. **Multi-language**: Works with "any language"
4. **Examples**: Concrete examples show usage patterns

### 2. analyze_image_async

**File**: `src/core/agents/tools/web_image_analyzer_tool.py`

**Agent Understanding**:
```
Tool Name: analyze_image_async

Description:
"Analyze images from URLs using OpenAI Vision API to extract
detailed visual information."

Parameters:
- image_url (required, string):
  "Full URL to the image to analyze. Must be valid HTTP/HTTPS URL
  pointing to accessible image (JPG, PNG, etc)."

- additional_context (optional, string):
  "Optional contextual information to improve analysis accuracy.
  Providing context helps focus on relevant details."
  Examples: "This is from post about apartments", "Customer asking about prices"

Returns:
"Detailed analysis including:
- All visible text and numbers (OCR)
- Key visual elements description
- Financial data if present (prices, trends)
- Structured info (dates, times, locations)
- Composition and style"

Use Cases:
✓ Instagram post/comment has image to analyze
✓ Customer asks about image content
✓ Need to extract text from images
✓ Financial charts need interpretation
✓ Product images need description

Don't Use:
✗ No image URL available
✗ Can answer without image

Capabilities:
- OCR (extract text)
- Analyze financial charts
- Describe products/offers
- Read schedules/calendars
- Identify visual elements
```

**Critical Information Agent Learns**:

1. **When to Use**: Clear triggers (post has image, customer references image)
2. **Capabilities**: Knows it can do OCR, chart analysis, etc.
3. **Context Value**: Understands providing context improves results
4. **Error Handling**: Returns descriptive errors if fails

## Best Practices Summary

### ✅ DO

1. **Be Explicit About Use Cases**
   ```
   USE THIS TOOL WHEN:
   - Specific scenario 1
   - Specific scenario 2
   ```

2. **Provide Clear Examples**
   ```
   Examples:
   - query: "квартиры в центре" → Returns apartments 85-95% confidence
   - query: "pizza" → Returns NOT FOUND (we don't sell pizza)
   ```

3. **Explain Parameter Impact**
   ```
   limit: Maximum number of high-confidence results to return.
          Default is 5, max is 10. Only results above 70%
          similarity threshold are returned.
   ```

4. **Document Return Variations**
   ```
   Returns:
   1. HIGH-CONFIDENCE RESULTS: Product list with details
   2. NO RELEVANT PRODUCTS: Nothing matches query
   3. DATABASE EMPTY: No products yet
   ```

5. **Include Anti-Patterns**
   ```
   DO NOT USE for:
   - General business questions
   - Contact information
   ```

### ❌ DON'T

1. **Vague Descriptions**
   ```python
   """Search for stuff"""  # ❌ What stuff? When to use?
   ```

2. **Missing Parameter Details**
   ```python
   """
   Args:
       query: The query  # ❌ What format? What should it contain?
   """
   ```

3. **No Examples**
   ```python
   # ❌ Agent doesn't see concrete usage patterns
   ```

4. **Unclear Return Values**
   ```python
   """Returns: Results"""  # ❌ What format? What do different results mean?
   ```

5. **No Use Case Guidance**
   ```python
   # ❌ Agent doesn't know WHEN to use this tool vs others
   ```

## Testing Tool Understanding

### Manual Test

Ask the agent questions that should trigger the tool:

```python
# Test embedding_search
"Do you have apartments in the city center?"
→ Should use embedding_search(query="apartments in city center")

"What pizza do you sell?"
→ Should use embedding_search(query="pizza")
→ Gets "NOT FOUND" → Politely declines

# Test analyze_image_async
"What's shown in this image? [URL]"
→ Should use analyze_image_async(image_url="...")

"Tell me about your business hours"
→ Should NOT use any tool (general question)
```

### Verify Agent Logs

Check agent execution logs to see:
1. Which tools were called
2. What parameters were passed
3. How agent interpreted the results

## Common Issues & Solutions

### Issue 1: Agent Uses Tool Incorrectly

**Symptom**: Agent calls tool with wrong parameters or at wrong time

**Solution**: Add more explicit use cases and anti-patterns to docstring
```python
"""
USE THIS TOOL WHEN:
- Very specific scenario A
- Very specific scenario B

DO NOT USE when:
- Common mistake scenario X
- Common mistake scenario Y
"""
```

### Issue 2: Agent Doesn't Use Tool When It Should

**Symptom**: Agent tries to answer without using available tool

**Solution**: Make tool description more prominent and add examples
```python
"""
Search for products using semantic similarity.

IMPORTANT: ALWAYS use this tool when customer asks about products.
Do not try to answer product questions without using this tool.

Examples:
- Customer: "Do you have X?" → Use this tool with query="X"
- Customer: "How much for Y?" → Use this tool with query="Y"
"""
```

### Issue 3: Agent Confused By Tool Output

**Symptom**: Agent misinterprets tool results

**Solution**: Be very explicit about return format and meanings
```python
"""
Returns:
    One of three clear outcomes:

    1. "✅ Found X result(s)" → Products found, use this information
    2. "⚠️ NO RELEVANT PRODUCTS FOUND" → Not in catalog, tell customer
    3. "⚠️ DATABASE EMPTY" → No products yet, suggest alternative

IMPORTANT: If you see "NO RELEVANT PRODUCTS FOUND", the customer's
requested item is NOT available. Inform them politely.
"""
```

## Conclusion

**Key Takeaway**: The docstring is the agent's instruction manual for the tool.

**Checklist for New Tools**:
- [ ] Clear one-line summary
- [ ] Detailed description of purpose
- [ ] Explicit "USE WHEN" section
- [ ] Clear "DON'T USE" section
- [ ] Detailed Args section with types and examples
- [ ] Clear Returns section with all variations
- [ ] Concrete Examples section
- [ ] Special notes for edge cases

**Remember**: The agent only knows what you tell it in the docstring!
