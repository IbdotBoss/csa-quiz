#!/usr/bin/env python3
"""Parse CSA-Master-Question-Bank.md into the app's question array.

Emits `const QS = [ ... ];` into _questions.js for splicing into index.html.
Paths resolve relative to this file, so no local path is ever published.
"""
import re, json, sys, pathlib

HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE.parent / "CSA-questions" / "CSA-Master-Question-Bank.md"

with open(SRC, encoding="utf-8") as f:
    text = f.read()

lines = text.splitlines()

# ---- Pass 1: parse answers from the domain answer tables ----
# rows look like: | Q87 ⭐ | A & D | key point |  OR  | Q1 | D | key point |
answers = {}   # qid -> (letters_list, explanation, is_real_from_answer)
ans_row = re.compile(r'^\|\s*Q(\d+)\s*(⭐)?\s*\|\s*([^|]+?)\s*\|\s*(.+?)\s*\|\s*$')
for ln in lines:
    m = ans_row.match(ln)
    if not m:
        continue
    qid = int(m.group(1))
    real = bool(m.group(2))
    letters_raw = m.group(3).strip()
    exp = m.group(4).strip()
    # parse letters: "A & D", "A, B & C", "A, B, C & D", "C", "D & E"
    letters = re.findall(r'\b([A-E])\b', letters_raw)
    if not letters:
        continue
    exp = exp.replace('**', '').strip()
    answers[qid] = (letters, exp, real)

# ---- Pass 2: parse questions ----
domain_hdr = re.compile(r'^##\s+Domain\s+(\d+)\s')
q_hdr = re.compile(r'^\*\*Q(\d+)\.\s*(⭐)?\*\*\s*(.*)$')
opt_line = re.compile(r'^\s*-\s*([A-E])\.\s+(.*)$')

questions = []
cur_domain = None
i = 0
n = len(lines)
in_answers = False
while i < n:
    ln = lines[i]
    dm = domain_hdr.match(ln)
    if dm:
        cur_domain = int(dm.group(1))
        in_answers = False
        i += 1
        continue
    if ln.strip().startswith('### Domain') and 'Answers' in ln:
        in_answers = True
        i += 1
        continue
    qm = q_hdr.match(ln)
    if qm and not in_answers:
        qid = int(qm.group(1))
        real_q = bool(qm.group(2))
        stem = qm.group(3).strip()
        # stem may continue on following lines until first option / blank
        j = i + 1
        # gather any continuation stem text before options
        opts = []
        while j < n:
            l2 = lines[j]
            om = opt_line.match(l2)
            if om:
                opts.append((om.group(1), om.group(2).strip()))
                j += 1
                continue
            if l2.strip() == '' and not opts:
                j += 1
                continue
            if l2.strip() == '' and opts:
                break
            if om is None and not opts and l2.strip() and not l2.startswith('**Q') and not l2.startswith('#'):
                # continuation of stem
                stem += ' ' + l2.strip()
                j += 1
                continue
            if l2.startswith('**Q') or l2.startswith('#') or l2.startswith('---'):
                break
            j += 1
        # clean stem: strip trailing (Choose N)/(Choose all...) markdown
        stem = re.sub(r'\s*\*?\(Choose[^)]*\)\*?\s*$', '', stem).strip()
        stem = stem.replace('**', '').strip()
        questions.append({
            'qid': qid,
            'd': cur_domain,
            'stem': stem,
            'opts': [o[1] for o in opts],
            'optletters': [o[0] for o in opts],
            'real_q': real_q,
        })
        i = j
        continue
    i += 1

def plain(s):
    """Bank is markdown; the app renders with textContent. Strip inline markup."""
    return s.replace('**', '').replace('`', '').strip()

# ---- Merge + build final objects ----
LET2IDX = {c: k for k, c in enumerate('ABCDE')}
out = []
errors = []
for q in sorted(questions, key=lambda x: x['qid']):
    qid = q['qid']
    if qid not in answers:
        errors.append(f"Q{qid}: no answer row found")
        continue
    letters, exp, real_ans = answers[qid]
    ans_idx = sorted(LET2IDX[c] for c in letters)
    nopts = len(q['opts'])
    if nopts < 2:
        errors.append(f"Q{qid}: only {nopts} options")
    for a in ans_idx:
        if a >= nopts:
            errors.append(f"Q{qid}: answer index {a} >= option count {nopts}")
    obj = {
        'id': qid,
        'd': q['d'],
        'q': plain(q['stem']),
        'opts': [plain(o) for o in q['opts']],
        'ans': ans_idx,
        'multi': len(ans_idx) > 1,
        'exp': plain(exp),
    }
    out.append(obj)

# ---- Validation report ----
print(f"Parsed {len(out)} questions", file=sys.stderr)
from collections import Counter
dc = Counter(o['d'] for o in out)
for d in range(1, 7):
    print(f"  D{d}: {dc.get(d,0)}", file=sys.stderr)
print(f"  multi: {sum(1 for o in out if o['multi'])}", file=sys.stderr)
if errors:
    print("ERRORS:", file=sys.stderr)
    for e in errors:
        print("  " + e, file=sys.stderr)
else:
    print("  no validation errors", file=sys.stderr)

# ---- Emit JS ----
parts = []
for o in out:
    parts.append(
        "{id:%d,d:%d,q:%s,opts:%s,ans:%s,multi:%s,exp:%s}" % (
            o['id'], o['d'],
            json.dumps(o['q'], ensure_ascii=False),
            json.dumps(o['opts'], ensure_ascii=False),
            json.dumps(o['ans']),
            'true' if o['multi'] else 'false',
            json.dumps(o['exp'], ensure_ascii=False),
        )
    )
js = "const QS = [\n" + ",\n".join(parts) + "\n];\n"
with open(HERE / "_questions.js", "w", encoding="utf-8") as f:
    f.write(js)
print("Wrote _questions.js", file=sys.stderr)
