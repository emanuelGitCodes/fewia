# Grocery chat direction

Mode: Operate. The primary task is a meal request followed by a budget-aware
estimate and explicit pantry revision. The generated concept is
[grocery-chat-concept.png](grocery-chat-concept.png).

Use a white page, forest-green text, pale sage assistant messages, fine borders,
and a two-column workspace. The conversation occupies the wider left column.
Budget inputs and the computed estimate occupy the right column. Below 800px,
place the budget controls before the conversation and estimate in one column.

Use a self-hosted Lora heading and Source Sans 3 interface text. The working
tokens are background #ffffff, ink #183f30, accent #20553d, muted #456357,
line #aabbb2, and message surface #f1f5ef. Use a 6px control radius, 16px body
text, 24px section titles, and a responsive 36px to 52px page heading.

The concept values are illustrative. The implementation MUST render computed
catalog values instead. Bean tacos for two currently cost $17.03 before pantry
exclusions. Do not retain the concept's incomplete four-row ingredient list.
Render every required ingredient. The default screen has no fabricated job.

Keep the sample-price notice near the estimate. Show the spending source and
model mode in plain text. Provide visible empty, queued, running, completed,
clarification, and failure states. Errors give a clear retry or correction action.
Disable repeat submission while a job is pending. All controls have labels,
keyboard focus, and adequate contrast. Do not add decorative metrics or charts.

The frontend uses React and Vite. Runtime data comes from the local backend.
The concept is a visual reference, not a screenshot of implemented behavior.
