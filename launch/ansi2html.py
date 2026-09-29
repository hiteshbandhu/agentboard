import sys, re, html
src = sys.stdin.read()
out = []; st = {'fg':None,'bg':None,'b':False,'i':False}
# Block elements drawn as solid fills: (fraction of the cell, from the top?)
BLOCKS = {'█': (1, False), '▀': (0.5, True), '▄': (0.5, False), '▔': (0.125, True),
          '▁': (0.125, False), '▂': (0.25, False), '▃': (0.375, False), '▅': (0.625, False),
          '▆': (0.75, False), '▇': (0.875, False)}

def esc(t):
    # every cell is exactly one column, whatever font the glyph falls back to
    r=[]
    for ch in t:
        if ch == '\n': r.append('\n')
        elif ord(ch) < 128: r.append(html.escape(ch))
        elif ch in BLOCKS:
            frac, top = BLOCKS[ch]
            fgc = st['fg'] or '#e8e8ea'
            bgc = st['bg'] or 'transparent'
            pct = frac * 100
            d = 'to bottom' if top else 'to top'
            r.append(f'<i class=c style="background:linear-gradient({d},{fgc} {pct}%,{bgc} {pct}%)"></i>')
        else: r.append(f'<i class=c>{html.escape(ch)}</i>')
    return ''.join(r)
def span(t):
    if not t: return ''
    css=[]
    if st['fg']: css.append(f"color:{st['fg']}")
    if st['bg']: css.append(f"background:{st['bg']}")
    if st['b']: css.append("font-weight:700")
    if st['i']: css.append("font-style:italic")
    return f'<span style="{";".join(css)}">{esc(t)}</span>' if css else esc(t)
pos=0
for m in re.finditer(r'\x1b\[([0-9;]*)m', src):
    out.append(span(src[pos:m.start()])); pos=m.end()
    codes=[int(c) if c else 0 for c in m.group(1).split(';')]
    i=0
    while i<len(codes):
        c=codes[i]
        if c==0: st.update(fg=None,bg=None,b=False,i=False)
        elif c==1: st['b']=True
        elif c==3: st['i']=True
        elif c==22: st['b']=False
        elif c==23: st['i']=False
        elif c==39: st['fg']=None
        elif c==49: st['bg']=None
        elif c in (38,48) and i+4<len(codes) and codes[i+1]==2:
            st['fg' if c==38 else 'bg']='#%02x%02x%02x'%tuple(codes[i+2:i+5]); i+=4
        i+=1
out.append(span(src[pos:]))
print('''<html><head><meta charset="utf-8"><style>
body{margin:0;background:#0c0c10;color:#e8e8ea}
pre{font:13.33px/17px "SF Mono",Menlo,monospace;margin:0;padding:12px}
i.c{display:inline-block;width:1ch;overflow:hidden;font-style:inherit;text-align:center;vertical-align:top;height:17px}
</style></head><body><pre>'''+''.join(out)+'</pre></body></html>')
