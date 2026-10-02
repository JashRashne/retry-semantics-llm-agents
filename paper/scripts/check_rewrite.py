#!/usr/bin/env python3
"""Read-only scientific checks; writes a presentation QA receipt, no reanalysis."""
from pathlib import Path
import argparse,csv,hashlib,json,math,re,subprocess,sys,unicodedata
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("--pdf-dir",default="build",help="PDF/log directory relative to paper")
parser.add_argument("--receipt",default="rewrite_review/PASS_C_QA.json",help="Receipt path relative to paper")
args=parser.parse_args()
P=Path(__file__).resolve().parent.parent;R=P.parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
q=P/'rewrite_review';protected=json.loads((q/'PASS_B_PROTECTED_INPUT_HASHES.json').read_text())
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip()==protected['HEAD']=='69cd125d6e987ce4f02cb9c0f04d004d19952641'
for path,digest in protected['protected_files'].items():assert sha(R/path)==digest,path
rows=list(csv.DictReader((P/'rewrite_plan/PASS_A_RESULTS_TABLES.csv').open()))
frozen=rows[:8];checked=[]
external=Path('/Users/jashrashne/Desktop/RetrySemantics_Final_Archive_20261001/study2_evidence/analysis/STUDY2_FINAL_ANALYSIS.json')
ext=json.loads(external.read_text())
# Compare presentation authority to existing source JSON; do not run estimators.
for r in frozen:
    source=Path(r['source_path']);assert sha(source)==r['source_sha256']
    if r['study'].startswith('Study 1'):
        a=json.loads(source.read_text())['primary'];w=a['worlds'][r['world']]
        ci=w['newcombe_paired_method10_95_ci'];pvalue=w['exact_mcnemar_raw_p']
        hp=a['holm']['tests'][r['world']]['holm_adjusted_p']
        assert float(r['Holm_adjusted_p'])==hp
    else:
        name={'GitHub':'github_canonical_coverage','Google Sheets replication':'sheets_post_incident_replication'}[r['study']]
        w=ext['populations'][name]['worlds'][r['world']];ci=w['ci_95'];pvalue=w['exact_mcnemar_p']
    assert int(r['N_pairs'])==w['N']
    for k,out in [('Replay_correct','replay_correctness'),('Regeneration_correct','regeneration_correctness')]:assert int(r[k])==w[out]['numerator']
    assert math.isclose(float(r['difference_Replay_minus_Regeneration_pp']),100*w['delta'],abs_tol=1e-12)
    for k,v in zip(['paired_CI_lower_pp','paired_CI_upper_pp'],ci):assert math.isclose(float(r[k]),100*v,abs_tol=1e-12)
    assert float(r['raw_McNemar_p'])==pvalue
    for k in ['n11','n10','n01','n00']:assert int(r[k])==w[k]
    checked.append({'study':r['study'],'world':r['world'],'N':w['N'],'source':str(source),'source_sha256':sha(source)})
md=(P/'manuscript.md').read_text();tex=(P/'main.tex').read_text();sm=(P/'supplement/manuscript.md').read_text()
title='Replay or Regenerate? Retry Semantics for State-Mutating LLM Agent Tool Calls Under Ambiguous Outcomes'
assert md.splitlines()[0]=='# '+title
assert next(line.strip() for line in tex.splitlines() if line.strip() and not line.lstrip().startswith('%'))==r'\documentclass[conference]{IEEEtran}'
assert next(line.strip() for line in (P/'supplement.tex').read_text().splitlines() if line.strip() and not line.lstrip().startswith('%'))==r'\documentclass[conference]{IEEEtran}'
assert not (P/'ieee_native_fonts.tex').exists()
for path in ['main.tex','supplement.tex','build_source.py','scripts/build_rewrite_assets.py']:
    source=(P/path).read_text()
    assert 'ieee_native_fonts.tex' not in source and '/System/Library/Fonts' not in source and 'Times New Roman' not in source
for term in ['executed/lost','gh-f020','results-lock','model amendment','POST_INCIDENT','canonical','Phase 3','Phase 4','approved','supersession','projection']:
    assert term not in md,term
abstract=md.split('## Abstract\n\n')[1].split('\n\n## Introduction')[0]
assert 170<=len(abstract.split())<=220
assert 'when the original action did not execute, four GitHub' in abstract
assert 'These results show why recovery must distinguish request identity' in abstract
assert not re.search(r'H[01]|H_[01]|Razorpay|canonical|hash|Phase',abstract)
assert 'maximum completion tokens' not in md+sm
assert 'executed/lost' not in md+sm+tex
for line in (md+'\n'+sm).splitlines():
    assert not re.search(r'(?<!DeepSeek )\bV4(?:\.1)?\b',line),line
assert not re.search(r'Correctness.*(?:⇔|iff|\\Leftrightarrow).*Observation',md)
assert not re.search(r'gh-f020|Phase [0-9]|approved context|canonical authority|analysis lock|frozen result context|supersession|POST_INCIDENT_',md)
assert '## Study 1B: model-transition replication' in md
assert 'No imputation changes the primary matched result.' in md
assert 'not a model-chosen omission' in md
assert 'zero behavioral observations' in md
assert 'No Regeneration state failure or budget exhaustion was recorded.' in md
razor=md.split('### Incomplete Razorpay attempt\n\n')[1].split('\n\n## Discussion')[0]
assert len(razor.split())<110 and len(razor.split('\n\n'))==1
main_table=(P/'tables/passb_results.tex').read_text()
for r in frozen:
    assert f"{r['Replay_correct']}/{r['N_pairs']} & {r['Regeneration_correct']}/{r['N_pairs']}" in main_table
    triple=[float(r[k]) for k in ['difference_Replay_minus_Regeneration_pp','paired_CI_lower_pp','paired_CI_upper_pp']]
    assert f'{triple[0]:+.1f} [{triple[1]:.1f}, {triple[2]:.1f}]' in main_table
sc=list(csv.DictReader((P/'rewrite_plan/PASS_A_SCENARIO_RESULTS.csv').open()))
assert len(sc)==8 and all(int(r['families'])==20 for r in sc)
assert [int(r['H1_Regeneration_failures']) for r in sc]==[0,1,0,2,0,2,0,4]
assert sum(int(r['H1_Regeneration_failures']) for r in sc)==9
paths=list(csv.DictReader((P/'rewrite_plan/PASS_A_ACTION_PATTERNS.csv').open()))
assert sum(int(r['count']) for r in paths)==640
for study in ['Study 1A','Study 1B']:
    for world in ['H0','H1']:
        selected=[r for r in paths if r['study']==study and r['world']==world]
        assert sum(int(r['count']) for r in selected)==160
        assert sum(int(r['budget_exhausted_count']) for r in selected)==0
assert ext['sheets_primary_incident']['eligible_behavioral_families']==0
budget=[r for r in ext['budget_state_cross_counts'] if r['dataset_id'].startswith('github') and r['hidden_world']=='H0']
assert sum(r['count'] for r in budget)==16
assert all(r['count']==0 for r in budget if r['state_correct']==0)
# Extract actual PDFs. Concatenate whitespace only for legitimately wrapped IDs.
pdfs={};build_errors=[]
for name in ['main','supplement']:
    file=P/args.pdf_dir/f'{name}.pdf';log=(P/args.pdf_dir/f'{name}.log').read_text()
    overfull=len(re.findall(r'Overfull \\[hv]box',log))
    undefined=len(re.findall(r'(?:Citation|Reference) .+? undefined|There were undefined (?:references|citations)|Undefined control sequence',log,re.I))
    font_warnings=len(re.findall(r'LaTeX Font Warning:',log))
    if overfull or undefined or font_warnings:
        build_errors.append({'document':name,'overfull_boxes':overfull,'undefined_citations_or_references':undefined,'font_substitution_warnings':font_warnings})
    raw=subprocess.check_output(['pdftotext','-raw',str(file),'-'],text=True)
    compact=re.sub(r'\s+','',raw)
    # Ordinary prose ligatures are not code corruption; exact identifiers below must extract unchanged.
    for token in ['accounts/fireworks/models/deepseek-v4-flash-0731','accounts/fireworks/models/deepseek-v4p1-flash']:
        assert token in compact,(name,token)
    if name=='main':
        extracted_abstract=raw.split('Abstract',1)[1].split('Index Terms',1)[0]
        norm=lambda v:re.sub(r'[^A-Za-z0-9]','',unicodedata.normalize('NFKC',v))
        if norm(extracted_abstract)!=norm(abstract):
            build_errors.append({'document':name,'pdf_abstract_does_not_match_current_source':True})
        for token in ['create_ticket','list_tickets','create_issue','list_issues','append_row','list_rows']:
            assert token in compact,token
    info=subprocess.check_output(['pdfinfo',str(file)],text=True)
    pages=int(re.search(r'Pages:\s+(\d+)',info)[1])
    if name=='main':assert pages<=9
    def include_text(path):
        t=path.read_text()
        for f in re.findall(r'\\input\{([^}]+)\}',t):
            fp=P/f
            if fp.exists():t+='\n'+include_text(fp)
        return t
    full=include_text(P/f'{name}.tex')
    labels=re.findall(r'\\label\{([^}]+)\}',full);refs=re.findall(r'\\ref\{([^}]+)\}',full)
    assert len(labels)==len(set(labels));assert set(refs)<=set(labels)
    assert set(labels)<=set(refs)
    if name=='main':
        assert sum(x.startswith('fig:') for x in labels)==2
        assert sum(x.startswith('tab:') for x in labels)==2
        bib=(R/'research/references.bib').read_text()
        cites={k for v in re.findall(r'\\cite\{([^}]+)\}',full) for k in v.split(',')}
        keys=set(re.findall(r'@\w+\{([^,]+),',bib));assert cites<=keys
    font_output=subprocess.check_output(['pdffonts',str(file)],text=True)
    font_rows=[line.split() for line in font_output.splitlines()[2:] if line.strip()]
    all_embedded=all(line[-5]=='yes' for line in font_rows)
    if not all_embedded:build_errors.append({'document':name,'unembedded_fonts':True})
    (q/f'PASS_C_{name.upper()}_FONTS.txt').write_text(font_output)
    pdfs[name]={'path':str(file),'pages':pages,'sha256':sha(file),'underfull_hboxes':len(re.findall(r'Underfull \\hbox',log)),'underfull_vboxes':len(re.findall(r'Underfull \\vbox',log)),'overfull_boxes':overfull,'undefined_references_or_citations':undefined,'font_substitution_warnings':font_warnings,'all_fonts_embedded':all_embedded,'font_names':[line[0] for line in font_rows],'identifier_extraction':'PASS; exact code strings recovered across layout line breaks'}
result={'status':'FAIL_FONT_QA' if build_errors else 'PASS','build_errors':build_errors,'pdf_directory':args.pdf_dir,'custom_system_font_dependency_removed_from_source':True,'standard_IEEEtran_first_operative_command':True,'candidate_publication_ready':not build_errors,'HEAD':protected['HEAD'],'protected_file_count':len(protected['protected_files']),'protected_inputs_unchanged':True,'bibliography_unchanged':True,'frozen_numeric_source_comparisons':checked,'main_result_rows_verified':8,'post_hoc_scenario_and_path_summaries_verified':True,'abstract_word_count':len(abstract.split()),'razorpay_disclosure_word_count':len(razor.split()),'main_figures':2,'main_tables':2,'pdfs':pdfs,'no_estimator_or_test_run':True,'no_new_collection_or_research_provider_request':True,'commit_or_push_performed':False,'visual_inspection':'All 8 main and 6 supplement candidate pages inspected; recorded separately in PASS_C_FINAL_AUDIT.md. This script does not perform visual inspection.'}
(P/args.receipt).write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'status':result['status'],'protected_file_count':result['protected_file_count'],'main_result_rows_verified':8,'pdfs':pdfs},indent=2))
sys.exit(1 if build_errors else 0)
