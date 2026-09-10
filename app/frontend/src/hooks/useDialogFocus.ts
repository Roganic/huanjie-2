import { useEffect, useRef } from 'react';

/** Shared keyboard behavior for modal sheets: contain focus, Escape, return focus. */
export function useDialogFocus(onClose: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  useEffect(() => { close.current = onClose; }, [onClose]);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const node = ref.current;
    if (!node) return;
    const controls = () => Array.from(node.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), summary, [tabindex="0"]')).filter(el => el.getClientRects().length);
    (controls()[0] ?? node).focus();
    function key(event: KeyboardEvent) {
      const top = Array.from(document.querySelectorAll('[aria-modal="true"], dialog[open]')).at(-1);
      if (top && top !== node) return;
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close.current(); }
      if (event.key !== 'Tab') return;
      const items = controls();
      if (!items.length) { event.preventDefault(); node?.focus(); return; }
      const first = items[0], last = items.at(-1)!;
      if (event.shiftKey && (document.activeElement === first || !node?.contains(document.activeElement))) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && (document.activeElement === last || !node?.contains(document.activeElement))) { event.preventDefault(); first.focus(); }
    }
    document.addEventListener('keydown', key);
    return () => { document.removeEventListener('keydown', key); if (previous?.isConnected) {
      if (previous.getClientRects().length) previous.focus();
      else previous.closest('details')?.querySelector('summary')?.focus();
    } };
  }, []);
  return ref;
}
