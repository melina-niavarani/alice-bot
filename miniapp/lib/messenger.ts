export type MiniApp={initData?:string;ready:()=>void;expand:()=>void;setHeaderColor?:(s:string)=>void;setBackgroundColor?:(s:string)=>void;BackButton?:{show:()=>void;hide:()=>void;onClick:(f:()=>void)=>void;offClick:(f:()=>void)=>void}};
declare global {interface Window {Telegram?:{WebApp?:MiniApp};Bale?:{WebApp?:MiniApp}}}
export function messenger(){return typeof window!=='undefined'&&new URLSearchParams(window.location.search).get('platform')==='bale'?'bale':'telegram'}
export function miniApp(){return messenger()==='bale'?window.Bale?.WebApp:window.Telegram?.WebApp}
