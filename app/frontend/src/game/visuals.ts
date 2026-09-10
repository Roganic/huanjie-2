export type ArtCategory = 'tavern' | 'wilds' | 'harbor' | 'ruins' | 'abstract' | 'portrait' | 'traveller' | 'weapon' | 'armor' | 'potion' | 'item';
export interface ArtSlot { asset_id?: string | null; builtin?: string | null; fallback?: ArtCategory | null; focal_x?: number; focal_y?: number }
export interface VisualAsset { name: string; source: 'upload' | 'generated'; data: string; generation_id?: string | null }
export interface ThemePack { schema_version?: 1; id: string; name: string; preset: 'parchment' | 'midnight' | 'neutral'; heading_font?: 'serif' | 'sans'; frame?: 'ornate' | 'simple'; illustrated?: boolean; assets?: Record<string, VisualAsset>; defaults?: Partial<Record<ArtCategory, ArtSlot>> }
export interface ModuleVisuals { schema_version?: 1; theme?: ThemePack; assets?: Record<string, VisualAsset>; scenes?: Record<string, ArtSlot>; characters?: Record<string, ArtSlot>; items?: Record<string, ArtSlot>; map?: Record<string, ArtSlot>; map_layout?: Record<string, {x:number; y:number; label?:string | null}>; player?: ArtSlot | null; cover?: ArtSlot | null }
export const themes: ThemePack[] = [
  { id: 'western-journal', name: '西境旅行志', preset: 'parchment', heading_font: 'serif', frame: 'ornate', illustrated: true },
  { id: 'moonlit-chronicle', name: '月下编年史', preset: 'midnight', heading_font: 'serif', frame: 'ornate', illustrated: true },
  { id: 'universal-atlas', name: '通用星图', preset: 'neutral', heading_font: 'sans', frame: 'simple', illustrated: false },
];
export const categoryNames: Record<ArtCategory, string> = { tavern: '室内 / 酒馆', wilds: '旷野 / 林地', harbor: '聚落 / 水岸', ruins: '遗迹 / 地下', abstract: '通用抽象背景', traveller: '冒险者', portrait: '人物徽记', weapon: '武器', armor: '防具', potion: '药剂', item: '物品 / 线索' };
export function themeOf(visuals?: ModuleVisuals | null) { return visuals?.theme || themes[0]; }
export function sceneCategory(name = ''): ArtCategory {
  if (/酒馆|客栈|室|屋|馆|tavern|inn\b/i.test(name)) return 'tavern';
  if (/遗迹|地下|墓|洞|crypt|dungeon|ruin/i.test(name)) return 'ruins';
  if (/港|渡|码头|河|海|城|镇|村|harbor|ferry|town|city/i.test(name)) return 'harbor';
  return 'wilds';
}
export function itemCategory(type = ''): ArtCategory { return type === 'weapon' ? 'weapon' : type === 'armor' ? 'armor' : type === 'consumable' ? 'potion' : 'item'; }
const icons: Record<string, string> = {
  portrait: '<circle cx="50" cy="34" r="13"/><path d="M22 80Q24 54 50 54Q76 54 78 80Z"/>',
  traveller: '<path d="M25 82L32 35Q50 7 68 35L75 82ZM32 35L50 50L68 35M50 50V82"/>',
  weapon: '<path d="M25 76L72 20L82 18L82 29L36 81M24 58L47 79M18 85L29 73"/>',
  armor: '<path d="M24 20L40 16Q50 33 60 16L76 20L86 41L71 49L71 84L29 84L29 49L14 41ZM39 45H61M50 35V70"/>',
  potion: '<path d="M40 18H60V38Q80 54 78 74Q75 87 50 87Q25 87 22 74Q20 54 40 38ZM35 18H65M28 62H72"/>',
  item: '<path d="M22 23H71L80 32V78H22ZM71 23V34H80M34 43H66M34 55H61M34 67H56"/>',
};
export function defaultArt(category: ArtCategory, illustrated = true): string {
  if (illustrated && ['tavern', 'wilds', 'harbor', 'ruins', 'traveller'].includes(category)) return `/art/western/${category}.png`;
  if (['tavern', 'wilds', 'harbor', 'ruins', 'abstract'].includes(category)) return '/art/atlas.svg';
  return `data:image/svg+xml,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" fill="#263c3a"/><circle cx="50" cy="50" r="46" fill="none" stroke="#7e8060"/><g fill="none" stroke="#e2cb9a" stroke-width="2.5" stroke-linejoin="round">${icons[category] || icons.item}</g></svg>`)}`;
}
export function builtinArt(builtin?: string | null, illustrated = true): string | null {
  return illustrated && builtin && ['tavern','wilds','harbor','ruins','traveller','village-square','marcus','ayla','hooded-merchant', 'dungeon-gate', 'dungeon-passage', 'ancient-temple', 'ancient-vault'].includes(builtin) ? `/art/western/${builtin}.png` : null;
}
export function resolveArt(visuals: ModuleVisuals | null | undefined, slot: ArtSlot | null | undefined, fallback: ArtCategory) {
  const theme = themeOf(visuals), category = slot?.fallback || fallback;
  const inherited = theme.defaults?.[category];
  const custom = slot?.asset_id ? visuals?.assets?.[slot.asset_id] : undefined;
  const shared = inherited?.asset_id ? theme.assets?.[inherited.asset_id] : undefined;
  const asset = custom || shared;
  const safe = asset?.data && /^data:image\/(png|jpeg);base64,[A-Za-z0-9+/=]+$/.test(asset.data) && asset.data.length <= 240000;
  const builtin = slot?.builtin || inherited?.builtin;
  const curated = builtinArt(builtin, theme.illustrated !== false);
  const focus = custom || (!shared && slot?.builtin) ? slot : inherited || slot;
  return { src: safe ? asset.data : curated || defaultArt(inherited?.fallback || category, theme.illustrated !== false),
    fallback: defaultArt(category, theme.illustrated !== false),
    position: `${focus?.focal_x ?? 50}% ${focus?.focal_y ?? 50}%`,
    source: safe ? asset.source : 'default' };
}
export function artImage(visuals: ModuleVisuals | null | undefined, slot: ArtSlot | null | undefined, fallback: ArtCategory, alt = '') {
  const art = resolveArt(visuals, slot, fallback), image = document.createElement('img');
  image.alt = alt; image.src = art.src; image.style.objectPosition = art.position;
  image.onerror = () => { image.onerror = null; image.src = art.fallback; };
  return image;
}
export function applyTheme(element: HTMLElement, visuals?: ModuleVisuals | null) {
  const theme = themeOf(visuals);
  element.dataset.illustrated = String(theme.illustrated !== false); element.dataset.theme = theme.preset; element.dataset.frame = theme.frame || 'ornate'; element.dataset.font = theme.heading_font || 'serif';
}

/** Portable uploads are decoded/re-encoded locally; no image or model API call. */
export async function prepareUpload(file: File): Promise<VisualAsset> {
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 8_000_000) throw new Error('请选择 8 MB 以内的 PNG、JPEG 或 WebP 图片。');
  const bitmap = await createImageBitmap(file);
  try {
    if (bitmap.width > 8192 || bitmap.height > 8192) throw new Error('原图边长请不超过 8192 像素。');
    const ratio = Math.min(1, 1200 / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement('canvas'); canvas.width = Math.max(1, Math.round(bitmap.width * ratio)); canvas.height = Math.max(1, Math.round(bitmap.height * ratio));
    const ctx = canvas.getContext('2d'); if (!ctx) throw new Error('当前浏览器无法处理图片。');
    ctx.fillStyle = '#e3d6b9'; ctx.fillRect(0, 0, canvas.width, canvas.height); ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    for (const quality of [.86, .72, .55, .38]) {
      const data = canvas.toDataURL('image/jpeg', quality);
      if (data.length <= 240000) return { name: file.name.slice(0, 120), source: 'upload', data };
    }
    throw new Error('图片细节较多，请先缩小后再上传。');
  } finally { bitmap.close(); }
}
