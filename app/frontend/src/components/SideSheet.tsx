import type { ReactNode } from 'react';
import { useDialogFocus } from '../hooks/useDialogFocus';
export default function SideSheet({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const ref = useDialogFocus(onClose);
  return <div className="sheet-overlay" onClick={onClose}>
    <div className="side-sheet" ref={ref} role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} onClick={e => e.stopPropagation()}>
      <div className="sheet-header"><h2>{title}</h2><button className="header-button" aria-label={`关闭${title}`} onClick={onClose}>关闭</button></div>
      <div className="sheet-body">{children}</div>
    </div>
  </div>;
}

export function DetailPanel({ modal, open, ...props }: { modal: boolean; open: boolean; title: string; onClose: () => void; children: ReactNode }) {
  return modal ? open ? <SideSheet {...props} /> : null : props.children;
}

export function ModalPanel({ title, className, onClose, children }: { title: string; className: string; onClose: () => void; children: ReactNode }) {
  const ref = useDialogFocus(onClose);
  return <div ref={ref} tabIndex={-1} className={className} role="dialog" aria-modal="true" aria-label={title} onClick={e => e.stopPropagation()}>{children}</div>;
}
