# How Jobs, Sessions and Turns Fit Together

This page explains the ideas behind two planned features: a job that is interrupted to ask a person and resumed with the answer, and a session that remembers what an agent has read across a conversation. It says what each thing is, why they are separate things, and why each is stored in the database and not in your program's memory.

> **This page describes a design that is not yet built.** It is written so the design can be agreed before the code is written. The names on this page may still change.

## The Problem Both Features Solve

An agent's work on one task is spread over time. It reads a file, thinks, and changes the file a minute later. It reaches a change that needs a person's approval, and the person answers after lunch. A chat application handles each message in a new request, often in another process.

Two things go wrong when nothing connects those moments. The agent writes over a change somebody else made after it read the file. And work that stopped to wait for a person cannot carry on, because the program that stopped it is gone.

VFS connects the moments with records it keeps in the database, each named by an id your application holds. Nothing important lives in one process's memory, so any process can pick the work up.

## VFS Never Waits

When a change needs a person, VFS does not ask the person and does not hold the call open. It stops before the change, saves what it needs to carry on, and returns at once. Your application asks the person in its own way, in a chat window or a ticket or an email. When the answer comes, your application hands it to VFS, and the work carries on from where it stopped.

What is saved is never a snapshot of a running program. It is the inputs of the work and the answers given so far, as plain data. To carry on, VFS starts the work again and feeds it the saved answers, so it arrives at the same point without doing anything twice. Every durable system studied for this design works this way, and none saves a running program.

## The Six Things

A [step](../reference/glossary.md#step) is one verb about to run, such as an edit of one file, with its arguments already checked.

A [policy](../reference/glossary.md#policy) is a function you write. VFS shows it each step before the step runs. The policy allows the step, denies it, or says a person must decide.

A [job](../reference/glossary.md#job) is one call you make through VFS. A direct call is a job of one step. A line of shell is a job of many. Most jobs finish inside the call and leave nothing behind. A job is stored only when it is stopped to wait for a person.

An [interrupt](../reference/glossary.md#interrupt) is what a stopped job is waiting for: a message for the person, the shape the answer must have, and a preview of what would change.

A [session](../reference/glossary.md#session) is VFS's side of one conversation: who the agent is, what it has been shown, and where its shell is.

A [turn](../reference/glossary.md#turn) is one message from the user and everything the agent does in answer. It divides a session's work into parts, and it is the point a session is taken back to.

## Why a Session Is Three Separate Things

The word "session" has meant several different things in the history of computing, and designs have failed where those things were merged. VFS keeps three apart.

The first is a context: who is acting, under which name, and where its shell is. The second is a record of what the agent has been shown. VFS calls each entry in that record a [stamp](../reference/glossary.md#stamp), and it is what stops a stale write. The third is the work the session started, which is its jobs.

They are separate because they behave differently. The record of what was seen is safe to lose. If a stamp is forgotten, the worst that follows is a refusal, and the agent reads the file again. So that record can be written a moment after each read and trimmed when it grows. A job is the opposite: a person may be about to answer it, so it must never be lost or copied. A fork of a session therefore copies what the session has seen and never takes its jobs. If the three were one object, a fork would have to choose one rule for all of them.

## Why an Id Is a Name and Never a Key

Your application chooses a session's id, usually the id it already has for the conversation. VFS stores the session under its owner and its id together. The owner is the authority that uses the session: the agent, and the people it acts for.

So the id opens nothing by itself. A caller who guesses another conversation's id gets a session of their own with that name, empty. Several projects that were studied skipped this and let any caller who knew an id use the session behind it. The ids in a chat application often come from the browser, so they must not be trusted as proof of anything.

## Why a Turn Has an Id of Its Own

A chat application lets a user edit an earlier message. The conversation keeps its id, and everything after that message is thrown away. No chat protocol tells the server this has happened. The server only receives a shorter history.

Your application knows which message was edited, so it tells VFS, by the turn's id. The same id can name the turn in your chat history and in your agent framework too, which is what lets all three go back to one point together. VFS does not try to detect an edit by itself. Servers that guess from the message list get it wrong.

## What a Rewind and a Fork Change

Both change what a session remembers, and both leave the files alone unless you ask otherwise.

A rewind takes one session back to before a turn. It forgets what the agent saw from that turn on, and what earlier turns saw comes back as it was. A fork starts a new session from that point and leaves the first one as it is.

The files are shared. There is one file system, and a fork works on the same files as its parent. Each session is protected from the other by its own record of what it has seen: when one changes a file, the other's next write to that file is refused until its agent reads it again. Every agent system that was studied shares files across a fork. The ones that tried to give each branch its own copy paid for it on every read.

A rewind can also put files back. VFS records what a session changed in each turn, so a rewind can restore exactly those files. It restores each one only when nobody else has changed it since, and it reports the ones it left alone. It never restores from a snapshot of a whole directory, which is how other tools came to overwrite other people's work.

## Why a Policy That Fails Refuses

A policy is a guard, and a broken guard should stop the work. If a policy raises an error, returns something that is not a decision, or takes too long, the step is refused. The other choice, letting the step through when its guard breaks, would turn every bug in a policy into a hole in it.

For the same reason a policy can only narrow what a caller may do. For a change, VFS checks the caller's rights first, and a policy is asked only about a change the caller already has the right to make.

## Where to Go Next

- [Keep a Session for Each Conversation](../how-to/keep-a-session-for-each-conversation.md) shows a session in use.
- [Interrupt a Job and Ask a Person](../how-to/interrupt-a-job-and-ask-a-person.md) shows a policy, an interrupt and a resume.
- [Planned API](../reference/planned-api/index.md) lists every name and argument.
