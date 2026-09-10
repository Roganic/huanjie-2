import { createRoot } from 'react-dom/client';
import './index.css';
import AuxiliaryPanels from './App';
import { AdventureController } from './game/controller';
import { mountAdventure } from './game/adventureEngine';

if (import.meta.env.VITE_BROWSER_ENGINE === 'true') {
  const status = document.createElement('div');
  status.id = 'runtime-loading'; status.setAttribute('role', 'status');
  status.textContent = '幻界 · 正在读取你的冒险…'; document.body.append(status);
  const { installBrowserEngine } = await import('./browserEngine');
  installBrowserEngine(message => {
    status.textContent = message;
    if (message === '冒险已准备好') status.remove();
    if (message.startsWith('无法准备冒险')) {
      const retry = document.createElement('button'); retry.textContent = '重新连接'; retry.onclick = () => location.reload(); status.append(retry);
    }
  });
}

const root = document.getElementById('root')!;
const stage = document.createElement('div'), panels = document.createElement('div');
root.replaceChildren(stage, panels);
const controller = new AdventureController();
const unmount = mountAdventure(stage, controller);
const auxiliaryRoot = createRoot(panels);
auxiliaryRoot.render(<AuxiliaryPanels controller={controller} />);
if (import.meta.hot) import.meta.hot.dispose(() => { unmount(); controller.destroy(); auxiliaryRoot.unmount(); });
