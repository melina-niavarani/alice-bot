export type Tariff = { label: string; price: number };
export type TariffSection = { title: string; items: Tariff[] };

// Only prices clearly established from Alice's tariff sheet and owner corrections.
export const tariffs: Record<'gym' | 'pool', TariffSection[]> = {
  gym: [
    {
      title: 'بدنسازی عمومی',
      items: [
        { label: '۸ جلسه', price: 1_800_000 },
        { label: '۱۲ جلسه', price: 2_000_000 },
        { label: '۱۶ جلسه', price: 2_200_000 },
        { label: '۲۰ جلسه', price: 2_500_000 },
      ],
    },
    {
      title: 'بدنسازی خصوصی',
      items: [
        { label: '۸ جلسه', price: 4_800_000 },
        { label: '۱۲ جلسه', price: 6_000_000 },
        { label: '۱۶ جلسه', price: 7_200_000 },
        { label: '۲۰ جلسه', price: 8_500_000 },
      ],
    },
    { title: 'برنامه بدنسازی', items: [{ label: 'برنامه', price: 1_200_000 }] },
  ],
  pool: [
    {
      title: 'آموزش شنا',
      items: [
        { label: '۸ جلسه', price: 9_900_000 },
        { label: '۱۰ جلسه', price: 11_500_000 },
      ],
    },
    {
      title: 'عضویت استخر و سونا',
      items: [
        { label: '۱۱ جلسه · دو ماهه', price: 8_000_000 },
        { label: '۲۲ جلسه · چهار ماهه', price: 16_000_000 },
      ],
    },
    { title: 'حمام سنتی', items: [{ label: 'ورودی', price: 1_100_000 }] },
    {
      title: 'ماساژ بهبود عضلانی',
      items: [
        { label: '۳۰ دقیقه', price: 1_300_000 },
        { label: '۶۰ دقیقه', price: 2_200_000 },
      ],
    },
    {
      title: 'ماساژ ریلکسی',
      items: [
        { label: '۳۰ دقیقه', price: 1_100_000 },
        { label: '۶۰ دقیقه', price: 1_800_000 },
      ],
    },
  ],
};

export function formatTariff(price: number) {
  return `${new Intl.NumberFormat('fa-IR').format(price)} تومان`;
}
