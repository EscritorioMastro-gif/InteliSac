// Contato enviado pelo cliente no WhatsApp (vCard): tira os números de telefone.
// "waid" é o número do WhatsApp da pessoa (o mais confiável); sem ele, usa os dígitos do TEL.

export function numerosDoVcard(vcard) {
  const nums = [];
  for (const linha of String(vcard || "").split(/\r?\n/)) {
    if (!/^(item\d+\.)?TEL[;:]/i.test(linha)) continue;
    const waid = linha.match(/waid=(\d+)/i);
    const n = waid ? waid[1] : linha.slice(linha.indexOf(":") + 1).replace(/\D/g, "");
    if (n && n.length >= 8 && !nums.includes(n)) nums.push(n);
  }
  return nums;
}

export function contatoDoVcard(cm) {
  return { name: cm?.displayName || null, numbers: numerosDoVcard(cm?.vcard) };
}
