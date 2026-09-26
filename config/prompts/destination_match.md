A paramedic said where the ambulance is going. You are given what was heard and the county's list of receiving
hospitals, each with an id and its official name. Paramedics use short names ("Good Sam", "Valley", "Regional",
"O'Connor", "Stanford", "Kaiser Santa Clara").

Return the ids of the listed hospitals the words name. Go through the list one hospital at a time and keep a
hospital only when every word the paramedic said fits that hospital's own name (a short form such as "Good Sam" for
"Good Samaritan" fits; "San Jose" fits only a name that contains "San Jose"; "Santa Clara" fits only a name that
contains "Santa Clara").
- One hospital kept: return it.
- Several kept, because the words are a system or brand name they share with no town or campus to tell them
  apart: return all of them.
- None kept (a street, a place, a hospital not on the list): return an empty list.
Never guess.
Return ONLY JSON: {"matches": ["<id>", ...]}
