import { useSyncExternalStore } from 'react';
import { ModalPanel } from './components/SideSheet';
import InventoryPanel from './components/InventoryPanel';
import ModulePanel from './components/ModulePanel';
import ModelSettings from './components/ModelSettings';
import StoryStudio from './components/StoryStudio';
import { AdventureController, apiUrl } from './game/controller';
import './game/auxiliary.css';

/** React remains only for auxiliary forms. The Phaser scene owns the game itself. */
export default function AuxiliaryPanels({ controller }: { controller: AdventureController }) {
  const view = useSyncExternalStore(controller.subscribe, controller.snapshot);
  const { state, panel } = view;
  if (!panel) return null;
  return <>
    {panel === 'inventory' && state && <InventoryPanel sessionId={state.session_id} apiUrl={apiUrl}
      visuals={view.visuals}
      pending={controller.locked} revision={view.revision} hp={state.actor?.hp || 0} hpMax={state.actor?.hp_max || 0}
      inCombat={state.game_phase === 'combat'} onChanged={() => controller.refresh()} onClose={controller.closePanel} />}
    {panel === 'modules' && <div className="module-panel-overlay"><ModalPanel title="选择冒险" className="module-dialog" onClose={controller.closePanel}>
      <ModulePanel modules={view.modules} activeModule={state?.active_module || null} loading={!!view.busy}
        onActivateModule={id => controller.activateModule(id)} onClose={controller.closePanel} />
      {view.error && <p role="status">{view.error}</p>}
    </ModalPanel></div>}
    {panel === 'settings' && <ModelSettings apiUrl={apiUrl} sessionId={state?.session_id || null}
      onClose={controller.closePanel} onSaved={label => controller.setNotice(label)} />}
    {panel === 'studio' && <StoryStudio apiUrl={apiUrl} onClose={controller.closePanel}
      onInstalled={() => controller.setNotice('模组已加入冒险库')} onPlay={id => controller.activateModule(id)} />}
  </>;
}
