"""Rescore saved observations without provider or database calls."""
import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

from app.evaluation_manifest import build_manifest
from app.evaluation_summary import summarize_evaluation
from app.evaluation_tool_score import score_tools

BASE = Path(__file__).resolve().parent
SOURCE = BASE.parent / 'benchmark-20261003/live-nova2-20261003/report.json'
CORPUS = BASE / 'corrected-scenarios.json'
OUTPUT = BASE / 'reproduced'
REVISION = 'e63d68f62cf8ae70dfd60d919bcc04f1d135c8a6'

def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main() -> None:
    OUTPUT.mkdir(exist_ok=False)
    original = json.loads(SOURCE.read_text())
    corpus = json.loads(CORPUS.read_text())
    cases = {case['id']: case for case in corpus['scenarios']}
    slots = deepcopy(original['slots'] + original['baseline_slots'])
    deltas = []
    for slot in slots:
        if slot['driver'] not in ('model', 'no_tool'):
            continue
        prior = deepcopy(slot['assessments']['tools'])
        corrected = score_tools(deepcopy(cases[slot['case_id']]), deepcopy(slot['observation']))
        if corrected != prior:
            assert slot['case_id'] in ('F04', 'F05')
            deltas.append({'case_id': slot['case_id'], 'repeat': slot['repeat'],
                           'condition': slot['condition'], 'before': prior, 'after': corrected})
        slot['assessments']['tools'] = corrected
    for before, after in zip(original['slots'] + original['baseline_slots'], slots, strict=True):
        other = deepcopy(after)
        other['assessments'] = deepcopy(before['assessments'])
        assert other == before
        assert {k: v for k, v in after['assessments'].items() if k != 'tools'} == {
            k: v for k, v in before['assessments'].items() if k != 'tools'}
    old_manifest = original['manifest']
    manifest = build_manifest(corpus, model_id=old_manifest['model_id'], region=old_manifest['region'], model_config=old_manifest['model_config'])
    for key in old_manifest:
        if key not in ('corpus_hash', 'manifest_hash'):
            assert manifest[key] == old_manifest[key]
    outputs = {
      'summary.json': summarize_evaluation(slots),
      'assessment-deltas.json': deltas,
      'corrected-manifest.json': manifest,
      'provenance.json': {
        'kind': 'post_hoc_gold_correction', 'new_inference_calls': 0,
        'derived_at': datetime.now(UTC).isoformat(),
        'observation_revision': original['revision'], 'scoring_revision': REVISION,
        'original_report_sha256': digest(SOURCE),
        'original_manifest_hash': old_manifest['manifest_hash'],
        'corrected_manifest_hash': manifest['manifest_hash'],
        'corrected_corpus_sha256': digest(CORPUS),
        'observations_unchanged': True, 'changed_assessment': 'tools',
        'changed_cases': ['F04', 'F05'], 'total_observation_slots': len(slots),
        'scope': 'Saved observations rescored with final-turn gold. Original benchmark remains authoritative for its original corpus. This is not a fresh inference batch.'}}
    for name, value in outputs.items():
        (OUTPUT / name).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'changed_slots': len(deltas), 'tool_group': next(g for g in outputs['summary.json']['groups'] if g['condition']=='tool_enabled'), 'manifest': manifest['manifest_hash']}, indent=2))

if __name__ == '__main__':
    main()
