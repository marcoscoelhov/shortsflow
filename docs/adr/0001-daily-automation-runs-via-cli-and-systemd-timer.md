# Daily automation runs via CLI and systemd timer

The daily automation cycle will be triggered by a systemd timer that calls an app CLI command, while the FastAPI hub remains responsible for visibility, configuration and manual operations. This keeps scheduled execution outside the web process, reduces duplicate execution risk when the hub or workers restart, and pairs with a database lock for the Sao Paulo local date to prevent concurrent cycles.

Operational amendment: backlog scheduling is candidate-based inside each slot. If a candidate can have visual-review debt repaired automatically but still keeps another manual requirement, the attempt is recorded and the cycle tries the next compatible candidate instead of burning the slot. This preserves auditability while keeping publication capacity usable.
