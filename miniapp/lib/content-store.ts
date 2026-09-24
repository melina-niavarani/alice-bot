import {env} from 'cloudflare:workers';
import {initialContent,type Content} from './content';
export function binding(){if(!env.DB)throw Error('Content database unavailable');return env.DB;}
export async function readContent(){const row=await binding().prepare('SELECT body, updated_at FROM club_content WHERE id = ?').bind(1).first<{body:string;updated_at:string}>();return row?{content:JSON.parse(row.body) as Content,updatedAt:row.updated_at}:{content:initialContent,updatedAt:null};}
export async function writeContent(content:Content){const updatedAt=new Date().toISOString();await binding().prepare('INSERT INTO club_content (id, body, updated_at) VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET body = excluded.body, updated_at = excluded.updated_at').bind(1,JSON.stringify(content),updatedAt).run();return updatedAt;}
