import {integer,sqliteTable,text} from 'drizzle-orm/sqlite-core';
export const clubContent=sqliteTable('club_content',{id:integer('id').primaryKey(),body:text('body').notNull(),updatedAt:text('updated_at').notNull()});
