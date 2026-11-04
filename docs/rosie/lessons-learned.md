# Lessons Learned

Findings from building and running ROSIE that shaped its design or operation.

## Retrieval and Answers

- **An empty search result is a real answer.** Responses should say that local documentation did not support the answer, rather than filling the gap from general knowledge.
- **Prompt size drives answer time on small GPUs.** On the Tesla P4, prompt processing dominates answer time. The system prompt was shortened from about 4,200 words to about 440, and evidence reduced from four passages to two, to speed up answers.
- **The same page can be found by both crawls.** The runbook index's pages are also reachable from the documentation site, so pages were stored twice under different kinds. They are now stored once, as runbooks.

## Runbooks

- **Runbooks are structured data first.** Markdown is an export format, not the source of truth, which keeps drafts consistent and makes other export formats possible.
- **Model output is a draft.** Review and the Git commit stay with the operator.

## Operations

- **Readiness depends on clean sources.** Chat waits for a sync with no errors, so a single broken link on the documentation site can keep chat unavailable after a restart. Keep source sites free of broken links, or check the sync status first when chat stays locked.
- **Services fail loudly.** Ingestion and search need the embedding server and Qdrant; answers and drafts also need the chat server. ROSIE reports these failures rather than answering without evidence.
- **The Tesla P4 needs active cooling help.** The passively cooled card reached 81 °C in the Supermicro chassis, whose BMC cannot see GPU temperature, and has logged NVIDIA Xid 79 ("GPU has fallen off the bus"). The thermal controller raises fan speed from the GPU temperature, but fan control cannot fix PCIe, power, driver, or hardware faults. If Xid errors recur, check system logs and physical cooling.
- **Pascal GPUs need CUDA 12 images.** CUDA 13 drops support for the P4's architecture, so the llama.cpp `server-cuda` (CUDA 12) image must be used.
