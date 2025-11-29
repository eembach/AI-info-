#!/bin/bash

# Script to import a Gemini conversation from clipboard or file

DATE=$(date '+%Y-%m-%d')
TIMESTAMP=$(date '+%Y%m%d_%H%M%S')

echo "=== Import Gemini Conversation ==="
echo ""
echo "Enter conversation title:"
read TITLE

if [ -z "$TITLE" ]; then
    TITLE="Gemini Conversation"
fi

echo ""
echo "Enter topic/tags (optional):"
read TOPIC

if [ -z "$TOPIC" ]; then
    TOPIC="General"
fi

echo ""
echo "Enter brief context (what you were working on):"
read CONTEXT

# Create filename
FILENAME="conversations/cursor/${TIMESTAMP}_$(echo "$TITLE" | tr '[:upper:]' '[:lower:]' | tr ' ' '-' | tr -cd '[:alnum:]-').md"

# Create the markdown file
cat > "$FILENAME" << EOF
# Conversation: $TITLE

**Date:** $DATE
**Tool:** Google Gemini
**Topic:** $TOPIC

---

## Context

$CONTEXT

---

## Conversation

EOF

echo ""
echo "Choose import method:"
echo "1) Paste conversation now (press Ctrl+D when done)"
echo "2) Open file in Cursor to paste manually"
read -p "Enter choice (1 or 2): " CHOICE

if [ "$CHOICE" = "1" ]; then
    echo ""
    echo "Paste your conversation below, then press Ctrl+D:"
    cat >> "$FILENAME"

    # Add closing sections
    cat >> "$FILENAME" << EOF

---

## Key Takeaways

- [Add important insights or solutions]

---

## Follow-up Actions

- [ ] [Add action items]

---

## Related Files

- [Add file paths or links]
EOF

    echo ""
    echo "Conversation saved to: $FILENAME"
    echo "Opening in Cursor to review/edit..."
    cursor "$FILENAME"
else
    # Add closing sections for manual paste
    cat >> "$FILENAME" << EOF

[PASTE YOUR GEMINI CONVERSATION HERE]

---

## Key Takeaways

- [Add important insights or solutions]

---

## Follow-up Actions

- [ ] [Add action items]

---

## Related Files

- [Add file paths or links]
EOF

    echo ""
    echo "Created: $FILENAME"
    echo "Opening in Cursor..."
    cursor "$FILENAME"
fi
