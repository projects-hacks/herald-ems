A paramedic said where the ambulance is going. You are given what was heard and the county's list of receiving
hospitals, each with an id and its official name. Paramedics use short names ("Good Sam", "Valley", "Regional",
"O'Connor", "Stanford", "Kaiser Santa Clara").

Return the id of the hospital the words name, or "none" when they name no hospital on the list, name more than one,
or could mean more than one. Before answering, check every listed name: if the words fit two or more of them (for
example a system or brand name that several listed hospitals share, with no town or campus to tell them apart),
return "none". Never guess.
Return ONLY JSON: {"id": "<id or none>"}
