#!/bin/bash

# Script to create a new conversation markdown file from template

# Get current date and time
DATE=$(date '+%Y-%m-%d')
TIMESTAMP=$(date '+%Y%m%d_%H%M%S')

# Prompt for conversation title
echo "Enter conversation title (or press Enter for default):"
read TITLE

# Use default title if none provided
if [ -z "$TITLE" ]; then
    TITLE="Cursor Conversation"
fi

# Create filename from title (replace spaces with dashes, lowercase)
FILENAME="conversations/cursor/${TIMESTAMP}_$(echo "$TITLE" | tr '[:upper:]' '[:lower:]' | tr ' ' '-' | tr -cd '[:alnum:]-').md"

# Copy template and replace placeholders
cp conversations/templates/conversation-template.md "$FILENAME"
sed -i "s/\[TITLE\]/$TITLE/g" "$FILENAME"
sed -i "s/\[DATE\]/$DATE/g" "$FILENAME"

echo "Created: $FILENAME"

# Open in Cursor if available
if command -v cursor &> /dev/null; then
    echo "Opening in Cursor..."
    cursor "$FILENAME"
else
    echo "Cursor not found in PATH. File created but not opened."
fi
