import { z } from 'zod';
const session = z.object({ day:z.string().max(30), start:z.string().regex(/^([01]\d|2[0-3]):[0-5]\d$/), end:z.string().regex(/^([01]\d|2[0-3]):[0-5]\d$/), audience:z.string().max(40) });
const service = z.object({description:z.string().max(2000), singlePrice:z.string().max(80), packagePrice:z.string().max(80), rules:z.string().max(4000), sessions:z.array(session).max(100)});
export const contentSchema = z.object({name:z.string().min(1).max(120), greeting:z.string().max(300), address:z.string().max(500), phone:z.string().max(40), gym:service, pool:service, notices:z.array(z.object({title:z.string().min(1).max(160),body:z.string().max(1600)})).max(30)});
export type Content = z.infer<typeof contentSchema>;
export const initialContent:Content = {
 name:'مجموعه ورزشی آلیس', greeting:'سلام، به آلیس خوش آمدی.', address:'تهران، تهرانپارس، خیابان شهید ملکی، نبش خیابان ۱۲۰، پلاک ۶', phone:'',
 gym:{description:'اطلاعات باشگاه بدنسازی، برنامه فعالیت و تعرفه‌ها.', singlePrice:'',packagePrice:'',rules:'',sessions:[]},
 pool:{description:'اطلاعات استخر و سونا، برنامه سانس‌ها و تعرفه‌ها.',singlePrice:'',packagePrice:'',rules:'',sessions:[]},
 notices:[]
};
