export const formatNumber = (value: string | number): string => {
  const numStr = typeof value === 'number' ? value.toString() : value;
  const number = numStr.replace(/[^0-9]/g, '');
  return number.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
};

export const parseNumber = (formattedValue: string): number => {
  return parseInt(formattedValue.replace(/,/g, ''), 10) || 0;
};
