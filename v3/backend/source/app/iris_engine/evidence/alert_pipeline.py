"""Finite, checkpointable map/reduce/verify plan. No database or provider imports."""
from copy import deepcopy
import hashlib
import json
import re

VERSION = 1
NODE_BYTES = 5500
MAX_FACTS = 12


class SplitPacket(ValueError):
    def __init__(self, message, *, provider_rejection=False):
        super().__init__(message)
        self.provider_rejection = provider_rejection


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def initial_state(packet_ids):
    return {'version': VERSION, 'stage': 'map', 'pending': list(packet_ids), 'mapped': [],
            'nodes': [], 'next_nodes': [], 'cursor': 0, 'level': 0, 'map_total': len(packet_ids),
            'mapped_count': 0, 'verified': [], 'unsupported': [], 'verify_cursor': 0,
            'verify_ref_cursor': 0, 'verify_supported': False, 'inferences': 0, 'cache_hits': 0}


def fact_view(fact):
    return {key: fact[key] for key in ('id', 'claim', 'kind', 'source_ids', 'quote') if key in fact}


def validate_node(value, references):
    """Only cite sources actually provided; store originals outside the prompt history."""
    if not isinstance(value, dict) or not isinstance(value.get('facts'), list):
        raise ValueError('Analysis returned invalid structured facts; retry this packet.')
    if len(value['facts']) > MAX_FACTS:
        raise ValueError('Analysis returned too many facts for one packet; retry with a smaller packet.')
    allowed = {ref['source_id'] for ref in references}
    facts = []
    for item in value['facts']:
        if not isinstance(item, dict) or not isinstance(item.get('claim'), str) or not item['claim'].strip():
            raise ValueError('Analysis returned an invalid claim; retry this packet.')
        sources = item.get('source_ids')
        if not isinstance(sources, list) or not sources or any(not isinstance(s, str) or s not in allowed for s in sources):
            raise ValueError('Analysis returned an unsupported source reference; retry this packet.')
        fact = {'claim': item['claim'].strip(), 'kind': item.get('kind', 'observation'),
                'source_ids': sorted(set(sources))}
        if isinstance(item.get('quote'), str) and len(item['quote']) <= 256:
            fact['quote'] = item['quote']
        if fact['kind'] not in ('observation', 'suspicious', 'benign', 'limitation'):
            raise ValueError('Analysis returned an invalid fact category.')
        fact['id'] = digest(fact)[:16]
        facts.append(fact)
    view = {'facts': facts}
    if len(json.dumps(view).encode()) > NODE_BYTES:
        raise ValueError('Intermediate facts exceed the bounded working memory; retry this packet.')
    return {**view, 'references': references}


def bind_references(node, store):
    """Locate literal quotes only in supplied ranges; retain ranges on missing/mismatched quotes."""
    for fact in node['facts']:
        refs = [r for r in node['references'] if r['source_id'] in fact['source_ids']]
        quote = fact.get('quote', '')
        if quote:
            for ref in refs:
                original = store.source(ref['source_id'])
                position = original.find(quote, ref['offset'], ref['end_offset'])
                if position >= 0:
                    refs = [{**ref, 'offset': max(ref['offset'], position - 96),
                             'end_offset': min(ref['end_offset'], position + len(quote) + 96)}]
                    break
        fact['references'] = refs
    return node


def _record_stats(state, response):
    state['inferences'] += int(not response.get('_cache_hit', False))
    state['cache_hits'] += int(response.get('_cache_hit', False))


def advance(state, store, infer):
    """Do at most one model request. `store` supplies immutable JSON get/put/source."""
    state = deepcopy(state)
    stage = state['stage']
    if stage == 'map':
        if not state['pending']:
            state.update(stage='reduce', nodes=state['mapped'], cursor=0)
            return state
        packet = store.get(state['pending'][0])
        try:
            response = infer('map', packet)
        except SplitPacket as exc:
            retries = packet.get('provider_retries', 0) + int(exc.provider_rejection)
            if retries > 2:
                raise ValueError('Provider context limit persists after two smaller-packet retries. Progress was saved.')
            references = packet['references']
            if len(references) > 1:
                middle = len(references) // 2
                groups = [references[:middle], references[middle:]]
            else:
                ref = references[0]
                start, end = ref['offset'], ref['end_offset']
                if end - start <= 256:
                    raise ValueError('The prompt and minimum evidence fragment exceed the safe context budget.')
                middle = (start + end) // 2
                # Overlap is evidence, not progress: complete original ranges remain represented.
                groups = [[{**ref, 'end_offset': min(end, middle + 64)}],
                          [{**ref, 'offset': max(start, middle - 64)}]]
            children = []
            for group in groups:
                text = '\n'.join(f"SOURCE {r['source_id']} [{r['offset']}:{r['end_offset']}]\n" +
                                 store.source(r['source_id'])[r['offset']:r['end_offset']] for r in group)
                children.append(store.put({'text': text, 'references': group,
                                           'provider_retries': retries}))
            state['pending'] = children + state['pending'][1:]
            state['map_total'] += 1
            return state
        node = bind_references(validate_node(response, packet['references']), store)
        identifier = store.put(node)
        state['mapped'].append(identifier)
        state['pending'].pop(0)
        state['mapped_count'] += 1
        _record_stats(state, response)
        return state
    if stage == 'reduce':
        if len(state['nodes']) <= 1:
            state.update(stage='verify', final_node=state['nodes'][0] if state['nodes'] else None)
            return state
        cursor = state['cursor']
        if cursor >= len(state['nodes']):
            state.update(nodes=state['next_nodes'], next_nodes=[], cursor=0, level=state['level'] + 1)
            return state
        nodes = [store.get(key) for key in state['nodes'][cursor:cursor + 2]]
        if len(nodes) == 1:
            state['next_nodes'].append(state['nodes'][cursor])
        else:
            refs = list({(r['source_id'], r['offset'], r['end_offset']): r
                         for node in nodes for fact in node['facts']
                         for r in fact.get('references', node['references'])}.values())
            response = infer('reduce', {'nodes': [{'facts': [fact_view(f) for f in n['facts']]} for n in nodes],
                                        'references': refs})
            state['next_nodes'].append(store.put(bind_references(validate_node(response, refs), store)))
            _record_stats(state, response)
        state['cursor'] += len(nodes)
        return state
    if stage == 'verify':
        node = store.get(state['final_node']) if state.get('final_node') else {'facts': []}
        cursor = state['verify_cursor']
        if cursor >= len(node['facts']):
            state.update(stage='final')
            return state
        fact = node['facts'][cursor]
        refs = fact.get('references', [r for r in node['references'] if r['source_id'] in fact['source_ids']])
        position = state['verify_ref_cursor']
        if position < len(refs):
            ref = refs[position]
            # Verification fragments use small bounded excerpts, never an entire large source.
            start = ref['offset'] + state.get('verify_fragment_offset', 0)
            end = min(ref['end_offset'], start + 512)
            excerpt = store.source(ref['source_id'])[start:end]
            response = infer('verify', {'fact': fact_view(fact), 'text': excerpt,
                                        'references': [{**ref, 'offset': start, 'end_offset': end}]})
            if type(response.get('supported')) is not bool:
                raise ValueError('Evidence verification returned an invalid answer; retry this packet.')
            state['verify_supported'] |= response['supported']
            if response['supported']:
                # Keep a concrete, verified original excerpt for the report citation.
                state['verified_reference'] = {**ref, 'offset': start, 'end_offset': end}
                state['verify_ref_cursor'] = len(refs)
            elif end == ref['end_offset']:
                state['verify_ref_cursor'] += 1
                state['verify_fragment_offset'] = 0
            else:
                state['verify_fragment_offset'] = end - ref['offset']
            _record_stats(state, response)
            return state
        if state['verify_supported']:
            state['verified'].append({**fact, 'reference': state.pop('verified_reference')})
        else:
            state['unsupported'].append(fact)
        state.update(verify_cursor=cursor + 1, verify_ref_cursor=0, verify_fragment_offset=0,
                     verify_supported=False)
        return state
    if stage == 'final':
        response = infer('final', {'facts': [fact_view(f) for f in state['verified']],
                                   'unsupported_count': len(state['unsupported']),
                                   'coverage': store.coverage})
        verdict = response.get('verdict')
        if verdict not in ('malicious', 'suspicious', 'likely_legitimate', 'insufficient_evidence'):
            raise ValueError('Analysis returned an invalid verdict; retry the final packet.')
        decisive = response.get('decisive_fact_ids', [])
        allowed = {fact['id'] for fact in state['verified']}
        if not isinstance(decisive, list) or any(not isinstance(key, str) or key not in allowed for key in decisive):
            raise ValueError('Analysis cited an unverified decisive fact; retry the final packet.')
        if not decisive or (verdict == 'likely_legitimate' and not store.coverage.get('source_complete')):
            verdict = 'insufficient_evidence'
        state.update(stage='completed', verdict=verdict, decisive_fact_ids=decisive)
        _record_stats(state, response)
        return state
    return state


def report(state, coverage, source_url):
    verdicts = {'malicious': 'Признаки вредоносной активности', 'suspicious': 'Подозрительная активность',
                'likely_legitimate': 'Вероятно легитимная активность', 'insufficient_evidence': 'Недостаточно доказательств'}
    lines = ['## Анализ оповещения', '', '**Вывод:** ' + verdicts[state['verdict']], '',
             f"Обработаны все доступные события: {coverage['available_events']}. "
             f"Отсутствуют связанные события: {len(coverage.get('missing_events', []))}."]
    if not coverage.get('source_complete'):
        lines += ['', '**Исходная цепочка неполная. Полное расследование не подтверждено.**']
    lines += ['', '### Проверенные наблюдения', '']
    for fact in state['verified']:
        ref = fact['reference']
        claim = re.sub(r'([\\`*_{}\[\]()#+.!<>|~])', r'\\\1', fact['claim'].replace('\n', ' ').replace('\r', ' '))
        lines.append('- ' + claim + f" ([источник]({source_url(ref)}))")
    if not state['verified']:
        lines.append('Нет подтверждённых исходными фрагментами наблюдений для уверенного вывода.')
    lines += ['', '### Ограничения и следующие действия', '',
              '- Просмотрены все уникальные пакеты доступного снимка; это не доказывает отсутствие ненаблюдаемых действий.',
              '- Выводы основаны на машинном обобщении; исходные данные сохранены для проверки аналитиком.']
    if state['unsupported']:
        lines.append(f"- Не подтверждены исходными фрагментами и исключены из вывода: {len(state['unsupported'])} утверждений.")
    if coverage.get('missing_events'):
        lines.append('- Получить отсутствующие связанные события и повторить анализ нового снимка.')
    lines.append('- Проверить исходные фрагменты и контекст срабатывания перед изменением статуса оповещения.')
    return '\n'.join(lines)
