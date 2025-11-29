# AI Conversation Logger

This directory contains recorded conversations from Cursor AI and Google Gemini.

## Workflow

### Recording New Conversations (Cursor)

1. Run the script to create a new conversation file:
   ```bash
   ./new-conversation.sh
   ```

2. Enter a title when prompted (or press Enter for default)

3. The script will:
   - Create a timestamped markdown file in `conversations/cursor/`
   - Open it automatically in Cursor

4. Copy and paste your conversation from Cursor into the opened file

5. Fill in the sections:
   - Context: What you were working on
   - Conversation: Your back-and-forth with the AI
   - Key Takeaways: Important insights or solutions
   - Follow-up Actions: What needs to be done next

### Importing Gemini Conversations

To import conversations from Google Gemini (gemini.google.com):

1. Run the import script:
   ```bash
   ./import-gemini-conversation.sh
   ```

2. Follow the prompts to enter:
   - Conversation title
   - Topic/tags
   - Brief context

3. Choose how to paste the conversation:
   - **Option 1**: Paste directly in terminal (then press Ctrl+D)
   - **Option 2**: Open in Cursor to paste manually

4. To get conversations from Gemini:
   - Go to https://gemini.google.com
   - Click on a conversation in your history
   - Select all (Ctrl+A) and copy (Ctrl+C)
   - Use the import script to save it

### Directory Structure

```
conversations/
├── cursor/          # Cursor AI and Gemini conversations
├── templates/       # Markdown templates
└── README.md        # This file
```

### File Naming Convention

Files are automatically named: `YYYYMMDD_HHMMSS_title.md`

Example: `20251129_163045_debug-api-error.md`

### Tips

- Use descriptive titles to make conversations easy to find
- Tag conversations with topics in the TOPIC field
- Link to related files at the bottom
- Add action items as you go
- Commit conversations to git regularly

### Manual Process

If you prefer not to use the script:

1. Copy the template: `cp templates/conversation-template.md cursor/my-conversation.md`
2. Open in Cursor: `cursor cursor/my-conversation.md`
3. Fill in the details manually

## Version Control

All conversations are tracked in this git repository. To save:

```bash
git add conversations/
git commit -m "Add conversation about [topic]"
git push
```
