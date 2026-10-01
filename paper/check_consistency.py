#!/usr/bin/env python3
"""Read-only paper checks against the frozen publication package; no reanalysis."""
import argparse,hashlib,json,re,subprocess
from pathlib import Path
P=Path(__file__).resolve().parent;R=P.parent
EXPECTED='671d1dff2e2995c14646cd5f46568430f606a749d6671cc608e9c9ee6950717d'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--publication-dir',type=Path,default=Path('/Users/jashrashne/Desktop/RetrySemantics_Archive/Final_Study2_Evidence_20261001/phase4_publication'));ap.add_argument('--receipt',type=Path);args=ap.parse_args();pub=args.publication_dir
 assert sha(pub/'PHASE4_REPRODUCIBILITY_MANIFEST.json')==EXPECTED
 # Delegate comprehensive sidecar/payload verification to unchanged approved verifier.
 result=subprocess.run(['python3',str(pub/'scripts/verify_publication.py'),'--publication-dir',str(pub)],check=True,capture_output=True,text=True)
 a=json.loads((pub/'reproducibility/sources/analysis/STUDY2_FINAL_ANALYSIS.json').read_text());s1=a['study1_locked_context']['primary_values_copied_not_recomputed'];s1w=s1['worlds']
 assert [(s1w[w][k]['numerator'],s1w[w][k]['denominator']) for w in ['H0','H1'] for k in ['replay_correctness','regeneration_correctness']]==[(160,160),(160,160),(0,160),(151,160)]
 def pp(x):return round(100*x,4)
 assert pp(s1w['H1']['delta'])==-94.3750
 assert [pp(x) for x in s1w['H1']['newcombe_paired_method10_95_ci']]==[-97.0128,-89.1060]
 assert pp(s1['interaction']['estimate'])==-94.3750
 assert [pp(x) for x in s1['interaction']['percentile_95_ci']]==[-97.5,-90.625]
 providers={x['dataset']:x for x in a['provider_summary']}
 assert [providers['github_canonical_coverage'][k] for k in ['canonical_arm_records','SUCCESS','FAILURE','INCONCLUSIVE','evaluable_arms','h0_matched_pairs','h1_matched_pairs','complete_families']]==[256,187,68,1,255,63,64,63]
 assert [providers['sheets_post_incident_replication'][k] for k in ['SUCCESS','FAILURE']]==[192,64]
 for name,counts in [('razorpay_original',[0,2,254]),('razorpay_paced_v1',[2,2,252]),('razorpay_host_v2',[7,5,244])]:assert [providers[name][k] for k in ['SUCCESS','FAILURE','unrun_opportunities']]==counts
 for name,expected in [('github_canonical_coverage',[[4.7619,-1.7819,13.0910],[-100,-100,-91.9921],[-104.7619,-111.1111,-100]]),('sheets_post_incident_replication',[[0,-5.6624,5.6624],[-100,-100,-91.9921],[-100,-100,-100]])]:
  pop=a['populations'][name]
  for w,values in zip(['H0','H1'],expected[:2]):
   v=pop['worlds'][w];assert [pp(v['delta']),*[pp(z) for z in v['ci_95']]]==values
  it=pop['interaction'];assert [pp(it['interaction']),pp(it['ci_95_lower']),pp(it['ci_95_upper'])]==expected[2]
 copies=[]
 for sub,glob,into in [('tables','*.csv','publication_data'),('figure_data','*.csv','publication_data'),('figures','*.pdf','figures')]:
  for source in sorted((pub/sub).glob(glob)):
   target=P/into/source.name;assert sha(target)==sha(source);copies.append({'source':str(source),'destination':str(target),'sha256':sha(source)})
 for name in ['TABLE_CATALOG.json','CAPTIONS.json']:
  source=pub/('tables' if name.startswith('TABLE') else 'figures')/name;assert sha(source)==sha(P/'publication_data'/name)
 baseline=json.loads((P/'phase5_review/PAPER_STATE_BEFORE.json').read_text())
 # Phase 5.1 authorizes bibliography metadata/citation changes; preserve its
 # prior SHA as a provenance anchor while still checking key integrity below.
 assert sha(R/'research/references.bib')!=baseline['bibliography_sha256']
 assert sha(R/'research/results/STUDY1_RESULTS_LOCK.md')==baseline['study1_lock_sha256']
 md=(P/'manuscript.md').read_text();tex=(P/'main.tex').read_text()
 inputs=re.findall(r'\\input\{([^}]+)\}',tex);assert len(inputs)==len(set(inputs))
 full=tex+'\n'+'\n'.join((P/f).read_text() for f in inputs)
 labels=re.findall(r'\\label\{([^}]+)\}',full);assert len(labels)==len(set(labels))
 refs=re.findall(r'\\ref\{([^}]+)\}',full);assert set(refs)<=set(labels)
 assert all(x in refs for x in labels if x.startswith(('fig:','tab:')))
 bib=(R/'research/references.bib').read_text();entries=re.findall(r'@\w+\s*\{\s*([^,\s]+)',bib)
 cites=set(k.strip() for keys in re.findall(r'\\cite\{([^}]+)\}',full) for k in keys.split(','));assert cites<=set(entries)
 assert len(entries)==len(set(entries))
 assert set(entries)==cites
 assert not re.search(r'metadata checked|user-specified reading target|publisher fetch blocked|needs manual verification|later venue not verified|audit commentary|ChatGPT',bib,re.I)
 assert not re.search(r'\[STUDY2-PENDING\]|Zero Study 2|zero Study 2 observations|complete[d]? GitHub replication|301 arms|Razorpay.*n\s*=\s*18|Interaction:.*p\s*=',md,re.I)
 assert 'POST_INCIDENT_REPLICATION_NOT_PRIMARY_REPLACEMENT' in md
 assert 'two predeclared observation opportunities subject to the frozen early-stop rules' in md
 assert 'without an imputed binary score' in md
 assert 'not a randomized causal intervention' in md
 assert 'retry correctness varies sharply with hidden execution state, while safe recovery also depends on what terminal state can be authoritatively established' in md
 assert '\x01' not in full
 # Key result/interpretation paragraphs stay literally equivalent to approved candidate.
 candidate=(pub/'manuscript/manuscript_candidate.md').read_text()
 catalog=json.loads((P/'publication_data/TABLE_CATALOG.json').read_text())
 matching_paragraphs=md.split('\n\n')+[t['note'] for t in catalog]
 approved=candidate.split('## 6. Study 2: external validation',1)[1].split('## 7. Discussion',1)[0]
 numeric_paragraphs=[]
 def numbers(s):
  s=re.sub(r'\\ref\{[^}]+\}|Table (?:A?[1-5])|Appendix A[12]','',s)
  return re.findall(r'(?<![A-Za-z])[-+]?\d+(?:\.\d+)?(?:e[-+]?\d+)?',s)
 for para in approved.split('\n\n'):
  if para.startswith(('#','|','**Table','Figure','!')) or not numbers(para):continue
  nums=numbers(para)
  assert any(numbers(m)==nums for m in matching_paragraphs),('Approved result paragraph numeric mismatch',para[:100],nums)
  numeric_paragraphs.append(para[:95])
 git_changed=subprocess.check_output(['git','diff','--name-only'],cwd=R,text=True).splitlines();assert all(f.startswith('paper/') or f=='research/references.bib' for f in git_changed)
 assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip()==baseline['HEAD']
 assert subprocess.check_output(['git','branch','--show-current'],cwd=R,text=True).strip()==baseline['branch']
 linked=R.parent/'retry_semantics_razorpay_host_v2';assert subprocess.check_output(['git','status','--short'],cwd=linked,text=True)==''
 receipt={'status':'PASS','approved_phase41_manifest_sha256':EXPECTED,'frozen_payload_check':json.loads(result.stdout),'prompt_checkpoint_comparison':'PASS; read from actual frozen Phase 3 JSON, no estimators run','approved_result_numeric_paragraphs_checked':len(numeric_paragraphs),'unchanged_quantitative_copies':copies,'phase51_bibliography_sha256':sha(R/'research/references.bib'),'prior_phase5_bibliography_sha256':baseline['bibliography_sha256'],'unchanged_study1_lock_sha256':sha(R/'research/results/STUDY1_RESULTS_LOCK.md'),'citation_keys':sorted(cites),'unused_existing_bibliography_entries':sorted(set(entries)-cites),'unique_figures':len([x for x in labels if x.startswith('fig:')]),'unique_tables':len([x for x in labels if x.startswith('tab:')]),'labels_references':'PASS; unique labels, all references defined, every table/figure referenced','linked_worktree_status':'clean','research_tracked_changes':['research/references.bib: bibliography-only edit authorized by Phase 5.1'],'scientific_evidence_modified':False,'reanalysis_performed':False}
 if args.receipt:args.receipt.write_text(json.dumps(receipt,indent=2)+'\n')
 print(json.dumps({k:v for k,v in receipt.items() if k!='unchanged_quantitative_copies'},indent=2))
if __name__=='__main__':main()
