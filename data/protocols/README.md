# County protocol documents (source for protocol lookup, P9)

One folder per county id in `config/counties/` (e.g. `santa_clara/`). Put the county's current, in-force PDFs
here exactly as published, keeping the county's file names. The knowledge index is rebuilt from these files, and
the county config (`config/counties/<id>.json`) lists the document ids and effective dates it was reviewed
against. When a newer version arrives, the county is flagged for review; the config is never rewritten
automatically.

Santa Clara (`santa_clara/`): 700-A13 Stroke, Policy 602 Patient Destination (and any Administrative Orders
amending it), Policy 501 Hospital Radio Reports, 700-S04 Routine Medical Care Adult, and the full Prehospital
Care Manual if available.
