from pathlib import Path
import csv,re,sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from build_source import inline
P=Path(__file__).resolve().parent.parent;T=P/'supplement/tables';T.mkdir(exist_ok=True)
def table(name,caption,label,headers,rows,cols=None,note=''):
    cols=cols or '@{}'+'l'*len(headers)+'@{}'
    s=[r'\begin{table*}[t]',r'\centering',r'\caption{'+inline(caption)+'}',r'\label{tab:'+label+'}',r'\begin{tabular}{'+cols+'}',r'\toprule',' & '.join(inline(x) for x in headers)+r' \\',r'\midrule']
    s+=[' & '.join(inline(str(x)) for x in row)+r' \\' for row in rows]
    s += [r'\bottomrule',r'\end{tabular}']
    if note:s+=[r'\par\smallskip\raggedright '+inline(note)]
    s+=[r'\end{table*}'];(T/f'{name}.tex').write_text('\n'.join(s)+'\n')
results=list(csv.DictReader((P/'rewrite_plan/PASS_A_RESULTS_TABLES.csv').open()))
frozen=results[:8]
table('tests','Retained exact paired test outputs. External p-values are unadjusted descriptive quantities. Full-precision paired effects and CIs remain in the supplementary results artifact.','s-tests',['Study','World','N','Raw p','Holm p'],[[r['study'].replace('Google Sheets replication','Sheets replication'),'$H_'+r['world'][1]+'$',r['N_pairs'],r['raw_McNemar_p'],r['Holm_adjusted_p'] or 'Not applied'] for r in frozen])
table('interactions','Retained complete-family interactions and percentile intervals (percentage points). No interaction p-value was frozen.','s-interactions',['Study','Complete families','Interaction','95% bootstrap CI'],[['Study 1A',160,'-94.375','[-97.5, -90.625]'],['Study 1B',160,'-100','[-100, -100]'],['GitHub',63,'-104.76190476190477','[-111.11111111111111, -100]'],['Sheets replication',64,'-100','[-100, -100]']])
table('marginal','Post-hoc descriptive 95% exact binomial boundary intervals. Working binomial model only; no scenario-clustering adjustment or new hypothesis test.','s-marginal',['Observed score','Marginal interval (%)'],[[r['population'],f"[{float(r['marginal_CP_lower_pct']):.2f}, {float(r['marginal_CP_upper_pct']):.2f}]"] for r in results if r['analysis_role']=='POST_HOC_DESCRIPTIVE_EXACT_BINOMIAL_ONLY'])
sc=list(csv.DictReader((P/'rewrite_plan/PASS_A_SCENARIO_RESULTS.csv').open()))
table('scenarios','Study 1A scenario results: post-hoc descriptive. Each template has 20 families; both policies score 20/20 in $H_0$ and Replay 0/20 in $H_1$ for every row.','s-scenarios',['ID','Scenario','Families','$H_1$ Regeneration','Failures'],[[r['scenario_id'],r['scenario_name'],r['families'],r['H1_Regeneration_correct']+'/20',r['H1_Regeneration_failures']] for r in sc])
actions=list(csv.DictReader((P/'rewrite_plan/PASS_A_ACTION_PATTERNS.csv').open()))
paths=lambda s:s.replace('create_ticket','write').replace('list_tickets','read').replace('MODEL_STOP','stop').replace(' -> ',' / ')
table('actions','Executed Regeneration action paths: post-hoc descriptive summaries. Every row ends with a model stop. Full member lists and hashes are in the supplementary action-pattern artifact.','s-actions',['Study','World','Action sequence','Count /160','Correct'],[[r['study'],'$H_'+r['world'][1]+'$',paths(r['pattern']),r['count'],r['state_correct_count']] for r in actions])
table('github_missing','Four $H_0$ Regeneration outcomes with a missing effect. All had complete final evaluator censuses and none exhausted budget.','s-github-missing',['Family','Reads','Write attempts','Write HTTP status','Terminal behavior'],[['2',2,1,'504','Dispatch unresolved'],['6',2,0,'Not applicable','Model stopped'],['15',2,0,'Not applicable','Model stopped'],['20',2,0,'Not applicable','Model stopped']])
table('source_identities','Selected artifact identities. The artifact evidence registry supplies the complete paths and hashes; these are existing sources, not new outputs.','s-identities',['Artifact','SHA-256'],[['Study 1A analysis', '`'+frozen[0]['source_sha256']+'`'],['Study 1B analysis','`'+frozen[2]['source_sha256']+'`'],['External paired table','`'+frozen[4]['source_sha256']+'`'],['GitHub archive','`32b7704318a22429a9402135fa9c518a13cc81c6dca9aa9912e15dde2a969385`'],['Family 20 original','`e39b1cc6e51139aa88192313a65e2fefb7fadb3edcf720273c51458be95ca494`']])
print('Rendered 7 supplement tables from stored results/descriptive summaries.')
