#!/usr/bin/env python3
"""Audit the built question data for anything a student should never see,
and for internal inconsistencies. Re-runnable; prints findings, exits 1 if any."""
import json, re, pathlib, sys, collections

QJS = pathlib.Path(r"C:\Users\uthma\Documents\ServiceNow\csa-quiz\_questions.js")
BANK = pathlib.Path(r"C:\Users\uthma\Documents\ServiceNow\CSA-questions\CSA-Master-Question-Bank.md")

raw = QJS.read_text(encoding="utf-8")
objs = re.findall(r'\{id:(\d+),d:(\d+),q:("(?:[^"\\]|\\.)*"),opts:(\[.*?\]),ans:(\[[^\]]*\]),'
                  r'multi:(true|false),src:("(?:[^"\\]|\\.)*"),exp:("(?:[^"\\]|\\.)*")\}', raw)
QS = []
for i, d, q, opts, ans, multi, src, exp in objs:
    QS.append(dict(id=int(i), d=int(d), q=json.loads(q), opts=json.loads(opts),
                   ans=json.loads(ans), multi=multi == "true",
                   src=json.loads(src), exp=json.loads(exp)))

findings = collections.OrderedDict()
def add(k, v):
    findings.setdefault(k, []).append(v)

# 1. internal bookkeeping language that means nothing to a student
LEAK = [
    (r'\bHarvested\b', 'says "Harvested" — internal provenance'),
    (r'docs clone', 'mentions "the docs clone" — internal'),
    (r'\bNot adjudicated\b', 'says "Not adjudicated" — internal'),
    (r'Community consensus', 'quotes community vote percentages'),
    (r'\bthe bank\b', 'refers to "the bank" — internal'),
    (r'harvested version', 'refers to a "harvested version"'),
    (r'⚠', 'carries a warning glyph'),
]
for q in QS:
    for pat, why in LEAK:
        if re.search(pat, q["exp"], re.I):
            add(why, f'Q{q["id"]}: {q["exp"][:88]}')

# 2. an explanation that does not actually explain (no reason given)
for q in QS:
    e = q["exp"].strip()
    if len(e) < 25:
        add("explanation too short to teach anything", f'Q{q["id"]}: {e!r}')

# 3. multi flag vs answer count
for q in QS:
    if q["multi"] != (len(q["ans"]) > 1):
        add("multi flag disagrees with answer count", f'Q{q["id"]}')

# 4. answer index out of range / duplicate options
for q in QS:
    if any(a >= len(q["opts"]) for a in q["ans"]):
        add("answer index beyond option list", f'Q{q["id"]}')
    if len(set(q["opts"])) != len(q["opts"]):
        add("duplicate option text", f'Q{q["id"]}')

# 5. cross-references to questions that do not exist
ids = {q["id"] for q in QS}
for q in QS:
    for ref in re.findall(r'\bQ(\d+)\b', q["exp"]):
        if int(ref) not in ids:
            add("explanation points at a question that does not exist", f'Q{q["id"]} -> Q{ref}')

# 6. near-duplicate questions inside the bank
STOP = set('a an the of to in is are for what which does do you your on with and or by as it '
           'that when where how at be admin user would should this these use used using can '
           'new from into their they it following servicenow'.split())
def toks(s):
    return set(w for w in re.findall(r'[a-z_]+', s.lower()) if w not in STOP and len(w) > 2)
T = [(q, toks(q["q"])) for q in QS]
for i in range(len(T)):
    for j in range(i + 1, len(T)):
        a, b = T[i][1], T[j][1]
        if not a or not b:
            continue
        jac = len(a & b) / len(a | b)
        if jac >= 0.6:
            add("near-duplicate question pair",
                f'Q{T[i][0]["id"]} / Q{T[j][0]["id"]} ({jac:.2f}): {T[i][0]["q"][:60]}')

# 7. domain map in the markdown vs what actually parsed
bank_txt = BANK.read_text(encoding="utf-8")
stated = dict((int(d), int(n)) for d, n in
              re.findall(r'^\| ([1-6]) \| .*? \| \**\d+%\** \| (\d+) \|$', bank_txt, re.M))
actual = collections.Counter(q["d"] for q in QS)
for d in range(1, 7):
    if stated.get(d) != actual.get(d):
        add("domain map disagrees with the questions",
            f'D{d}: map says {stated.get(d)}, parsed {actual.get(d)}')
m = re.search(r'\| — \| \*\*Total\*\* \| 100% \| \*\*(\d+)\*\* \|', bank_txt)
if m and int(m.group(1)) != len(QS):
    add("domain map disagrees with the questions",
        f'total: map says {m.group(1)}, parsed {len(QS)}')

print(f"audited {len(QS)} questions\n")
if not findings:
    print("clean")
    sys.exit(0)
for k, v in findings.items():
    print(f"[{len(v)}] {k}")
    for line in v[:6]:
        print(f"      {line}")
    if len(v) > 6:
        print(f"      ... and {len(v)-6} more")
    print()
sys.exit(1)
