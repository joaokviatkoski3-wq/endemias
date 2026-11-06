"""Subconjunto explícito de XPath usado pelas definições Kobo consultadas.

Não executa Python/JavaScript nem aceita funções externas. A AST também pode
ser consumida pela interface, mantendo as mesmas regras no servidor.
"""
import re

TOKEN=re.compile(r"\s*(\$\{[^}]+\}|'[^']*'|\"[^\"]*\"|>=|<=|!=|=|>|<|\(|\)|,|\d+(?:\.\d+)?|\.|[A-Za-z_][A-Za-z0-9_-]*)")
FUNCTIONS={'not','selected','count-selected','string-length','normalize-space','date','true','false','if','string','number'}


def analisar(expression):
    if expression in (None,'',True):return ['literal',True]
    if expression is False:return ['literal',False]
    if not isinstance(expression,str) or len(expression)>4000:raise ValueError('Condição inválida.')
    tokens=[];pos=0
    while pos<len(expression.strip()):
        match=TOKEN.match(expression,pos)
        if not match:raise ValueError('Condição Kobo não suportada; revisar definição.')
        tokens.append(match[1]);pos=match.end()
    index=0
    def peek():return tokens[index] if index<len(tokens) else None
    def take(value=None):
        nonlocal index
        current=peek()
        if current is None or value is not None and current!=value:raise ValueError('Condição incompleta.')
        index+=1;return current
    def atom():
        value=take()
        if value=='(':
            node=logic();take(')');return node
        if value.startswith('${'):return ['ref',value[2:-1]]
        if value.startswith(("'",'"')):return ['literal',value[1:-1]]
        if re.fullmatch(r'\d+(?:\.\d+)?',value):return ['literal',float(value)]
        if peek()=='(':
            if value not in FUNCTIONS:raise ValueError('Função de condição não suportada.')
            take('(');args=[]
            if peek()!=')':
                args.append(logic())
                while peek()==',':take(',');args.append(logic())
            take(')');return ['call',value,args]
        return ['ref',value]
    def comparison():
        node=atom()
        if peek() in ('=','!=','>','<','>=','<='):
            op=take();node=['compare',op,node,atom()]
        return node
    def conjunction():
        node=comparison()
        while peek()=='and':take();node=['and',node,comparison()]
        return node
    def logic():
        node=conjunction()
        while peek()=='or':take();node=['or',node,conjunction()]
        return node
    tree=logic()
    if index!=len(tokens):raise ValueError('Condição contém conteúdo não suportado.')
    return tree


def avaliar(tree, values, current='', choice=None):
    op=tree[0]
    if op=='literal':return tree[1]
    if op=='ref':return current if tree[1]=='.' else (choice or {}).get(tree[1],values.get(tree[1],''))
    if op=='and':return bool(avaliar(tree[1],values,current,choice)) and bool(avaliar(tree[2],values,current,choice))
    if op=='or':return bool(avaliar(tree[1],values,current,choice)) or bool(avaliar(tree[2],values,current,choice))
    if op=='call':
        name=tree[1];args=[avaliar(a,values,current,choice) for a in tree[2]]
        if name=='true':return True
        if name=='false':return False
        if name=='not':return not args[0]
        if name=='selected':return str(args[1]) in str(args[0]).split()
        if name=='count-selected':return len(str(args[0]).split())
        if name=='string-length':return len(str(args[0]))
        if name=='normalize-space':return ' '.join(str(args[0]).split())
        if name=='date':return str(args[0])
        if name=='if':return args[1] if args[0] else args[2]
        if name=='number':
            try:return float(args[0])
            except (ValueError,TypeError):return float('nan')
        if name=='string':
            v=args[0]
            return str(int(v)) if isinstance(v,float) and v.is_integer() else str(v)
    if op=='compare':
        a=avaliar(tree[2],values,current,choice);b=avaliar(tree[3],values,current,choice);cmp=tree[1]
        if cmp in ('=','!='):
            equal=str(a)==str(b) if not isinstance(a,(int,float)) or not isinstance(b,(int,float)) else a==b
            return equal if cmp=='=' else not equal
        if isinstance(a,(int,float)) or isinstance(b,(int,float)):
            try:a=float(a);b=float(b)
            except (TypeError,ValueError):return False
        if cmp=='>':return a>b
        if cmp=='<':return a<b
        if cmp=='>=':return a>=b
        if cmp=='<=':return a<=b
    raise ValueError('Condição não suportada.')
