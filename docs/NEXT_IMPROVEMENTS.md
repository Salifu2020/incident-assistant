# Next improvements

A fresh batch after the local store, stricter “not in your documents” answers, real library status, the slim sidebar, the answer card, and upload Ready / Still indexing.

Sign-in lockout (backend 6) is done. Six wrong passwords lock the next try for 15 minutes, the count lives on the JSON user record, and every failure returns “Invalid email or password.” The Postgres user store still does not lock accounts.

History, Saved questions, and Users (frontend 6) are done. They use the same centered title, type, and plain buttons as Library and Upload. The old metric tiles, emoji headings, and close buttons are gone. Users stays admin-only.

Saved threads (backend 1) are done. Every streamed question sends the conversation id. The question and the answer are stored with sources and the confidence line, and the first question becomes the title in Recent. A follow-up is answered from the previous turns. New chat starts blank, and the row is created with the first question.

Each item is one change. Render the answer is the one to do before anything else.

## Do these first

1. **Render the answer as writing, not raw markdown** (frontend). Lists and bold currently show up as `*` and `**` inside the card.

## Backend

### 1. Save the thread and answer follow-ups — done

Every streamed question includes the conversation id. The user turn and the assistant turn are saved, including sources and the confidence line. The first question replaces a “Conversation N” title. The next question receives the last few turns in retrieval and in the prompt, so a follow-up such as “what about the second job?” stays on the same document. Reopening the chat restores the messages, the confidence line, and the sources.

### 2. Keep each account’s documents separate

Uploads land in one shared Chroma collection. Any signed-in user can search and delete files another account uploaded. Analytics records `user_id` as empty.

Stamp every chunk with the uploader’s user id. Filter retrieval, the library, delete, and reprocess by that id. Admins can still see everything.

Done when the demo account cannot see or ask about a file uploaded by another user.

### 3. Cite a page, not only a filename

PDF text is concatenated before chunking, so the page number is thrown away. Source chips can only say the file name and High / Medium / Low.

Store `page` (and a short heading when one exists) on each chunk. Return it with the source. Deduplicate by file + page, keeping the stronger passage.

Done when a resume or policy answer can say “page 2” and two chunks from the same page collapse into one source.

### 4. Stop citing near-duplicate files

Two copies of the same resume both come back as separate sources. That makes confidence look broader than the evidence is.

When two chunks are almost the same text, keep the one with the higher relevance and name the file it came from.

Done when “Summarize the resume” cites one resume, not `resume.pdf` and `resume_fresh.pdf` side by side, unless their text actually differs.

### 5. A small set of questions that must keep working

The refusal threshold and the reranker are easy to “improve” into guessing again, or into refusing real answers.

Add about 15 fixed questions: some that are in the sample documents, some that are not. Run them against the local API and record whether the reply was a refusal, which file was cited, and the confidence level.

Done when that check can be run with one command before a retrieval change.

### 6. Lock accounts after repeated bad passwords — done

Six wrong passwords set `failed_attempts` and `locked_until` on the JSON user. The next try is rejected for 15 minutes, including the correct password. When the window ends, the correct password works and the count resets. Wrong password, unknown email, and a lock all return “Invalid email or password.” Checked in `tests/test_login_lockout.py`.

## Frontend

### 1. Format the answer inside the card

The card escapes the whole reply, so a model list becomes one paragraph with asterisks. The confidence line and sources should stay as they are.

Render a small, safe subset inside the answer body: paragraphs, bold, and lists. Leave the footer (confidence, collapsed sources) untouched.

Done when a resume summary shows job titles as a list, and the confidence line still sits under the divider.

### 2. Let the live answer use the same card

While tokens are streaming, the reply is a plain bubble. When the stream ends it jumps into the answer card.

Stream into the card body. Show the confidence line and the source summary only when the stream finishes.

Done when the text never changes container at the end of an answer.

### 3. Put “search these documents” back, quietly

The sidebar control is gone, but the ask payload still sends `selected_documents` if something set it. There is no way to set it.

Add a single control on the composer or the library: “All documents” or a chosen few. Show the choice as one line under the chat box when it is not “all”.

Done when a question about a resume can be limited to that file, and a new chat starts on all documents again.

### 4. Open a source instead of only naming it

Chips show the filename and High / Medium / Low. They do not open the passage.

Make each chip expand to the quoted passage (and the page, once the backend stores it). Keep the list collapsed by default.

Done when opening “3 sources” shows the sentence the answer used, not only the file name.

### 5. Hide empty chats in Recent

Older empty “Conversation N” rows are still in the dropdown. New chat starts blank, and a row is saved with the first question.

List only conversations that have at least one message. Keep New chat as the way to start a blank one.

Done when Recent shows titled threads only.

### 6. Make History, Saved questions, and Users match the home — done

History lists each question with its time, plus Ask, Delete, and Clear history. Saved questions uses Ask, Edit, and Delete. Users shows one row per account, with Make admin, Deactivate, and Unlock. No new actions were added. Users is still admin-only.

## Leave for later

- Render and any other public host. Local is the working setup.
- A new model or embedding change. Do the question set in backend item 5 first, then compare.
- Two-factor authentication. Accounts are not isolated yet, so a second factor does not protect the documents.
