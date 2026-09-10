import { resolveArt, type ArtCategory, type ArtSlot, type ModuleVisuals } from '../game/visuals';
export default function ArtImage({ visuals, slot, fallback, className = '' }: { visuals?: ModuleVisuals | null; slot?: ArtSlot | null; fallback: ArtCategory; className?: string }) {
  const art = resolveArt(visuals, slot, fallback);
  return <img className={className} src={art.src} alt="" style={{ objectPosition: art.position }} onError={e => { if (e.currentTarget.getAttribute('src') !== art.fallback) e.currentTarget.src = art.fallback; }} />;
}
