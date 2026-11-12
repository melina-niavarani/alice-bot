export type Tariff = { label: string; price: number };
export type TariffSection = { title: string; items: Tariff[] };

// Prices are displayed in toman. The autumn 1405 gym sheet lists amounts in rial.
export const tariffs: Record<'gym' | 'pool', TariffSection[]> = {
  gym: [
    {
      title: 'بدنسازی خصوصی (تک‌نفره)',
      items: [
        { label: '۱۲ جلسه', price: 16_850_000 },
      ],
    },
    {
      title: 'بدنسازی خصوصی (تا سه نفر)',
      items: [
        { label: '۱۰ جلسه', price: 5_500_000 },
        { label: '۱۲ جلسه', price: 6_000_000 },
        { label: '۱۶ جلسه', price: 7_200_000 },
      ],
    },
    {
      title: 'ورودی ترکیبی بدنسازی و استخر',
      items: [
        { label: '۱ جلسه', price: 1_100_000 },
      ],
    },
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
