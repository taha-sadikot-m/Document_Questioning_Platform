## Overview

Build a mini document intelligence system that allows a user to:

1. Upload PDFs
2. Ask questions about them
3. Receive answers with citations from the documents
4. (Bonus) Suggest insights or next steps based on the documents

## Requirements

Core Features

- Upload 1-50 PDFs
- Parse + process documents
- Ask natural language questions
- Return:
- Answer
- Cited sources (exact chunks or references)

## Technical Expectations

You are free to use any tools (including LLMs), but you must:

- Show a clear architecture
- Implement:
- document ingestion
- chunking strategy
- embeddings + retrieval
- answer generation
- Handle basic edge cases (e.g., empty PDFs, irrelevant queries)

## N-ERGY Intern Take-Home Assignment

## Constraints

You must optimize for ONE of the following:

- Latency (fast responses)

OR

- Accuracy (higher quality answers)

You need to clearly state which one you chose and why.

## Development Environment

- To ensure consistency and make evaluation easier, you will complete this assignment on a shared development environment hosted by us.
- The development environment includes access to Claude Code, which you may use to assist with development if helpful.
- You are also free to use any other tools or workflows you prefer.
- However, in the next round, you will be expected to clearly explain your implementation, justify your decisions, and make modifications to your system.

## Step 1: Send your SSH key

- Please email us:
- Your public SSH key (either as a .pub file or pasted in the email)
- We will use this to grant you access to the environment.

## Step 2: Access the environment

- Once access is granted, you can connect using:
- ssh guestuser@ec2-3-239-244-156.compute-1.amazonaws.com

## Step 3: Build your solution

- You may build your solution directly on this machine
- You are free to install dependencies as needed
- Please keep your work organized in a clearly named directory

## Step 4: Submission requirements on the environment

- Your final code should be present on the machine
- Your README should include instructions on how to run your solution

## Deliverables

1. Code
- GitHub repo
- Clean, runnable code

## 2. README (required)

Keep it concise but include:

- Architecture overview
- Key design decisions
- Tradeoffs you made
- What would break at scale (e.g., 10k+ documents)
- What you would improve with more time

## Time Expectation

- Target: 8 hours
- We value clarity + decision-making over completeness

## Important Note

- You may use AI tools while building.

However, in the next round, you will be asked to:

- explain your system in detail
- justify decisions
- modify or extend parts of your system live

## Submission

- Send:
- GitHub repo link
- README