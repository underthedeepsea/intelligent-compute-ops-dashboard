"""Deterministic replay-only hysteresis. Production policies remain upstream-owned."""
def evaluate_window(state, value, rule, step, valid=True):
    state.setdefault('level','NORMAL')
    for k in ('high','error','below_error','clear'): state.setdefault(k,0)
    state.setdefault('first', None)
    if not valid:
        for k in ('high','error','below_error','clear'): state[k] = 0
        return 'UNKNOWN', None, False
    level = 'CRITICAL' if value >= rule['critical'] else 'WARNING' if value >= rule['warning'] else 'NORMAL'
    state['high'] = state['high']+1 if level!='NORMAL' else 0
    state['error'] = state['error']+1 if level=='CRITICAL' else 0
    state['below_error'] = state['below_error']+1 if level!='CRITICAL' else 0
    state['clear'] = state['clear']+1 if level=='NORMAL' else 0
    active = state['level'] != 'NORMAL'
    if state['error'] >= rule['confirm_windows']:
        state['level'] = 'CRITICAL'
    elif not active and state['high'] >= rule['confirm_windows']:
        state['level'] = 'WARNING'
    elif state['level']=='CRITICAL' and state['below_error'] >= rule['recover_windows']:
        state['level'] = 'WARNING'
    if state['clear'] >= rule['recover_windows']:
        state['level'] = 'NORMAL'; state['first'] = None
    if state['level'] != 'NORMAL':
        if state['first'] is None: state['first'] = max(0, step-rule['confirm_windows']+1)
        return state['level'], {'level':state['level'],'value':value,'first_step':state['first'],
                               'matched':state['high'],'clear':state['clear'],
                               'error_streak':state['error']}, False
    # A first breach is PENDING, never a claimed normal observation.
    pending = level != 'NORMAL'
    return ('UNKNOWN' if pending else 'NORMAL'), None, pending
