import { test, expect } from '@playwright/test';

const STORE_URL = 'file:///Users/ddz/Dev/e2e-agent/demo_app/index.html';

test('store-e2e-flow', async ({ page }) => {
  await test.step('navigate-home: Navigate to the store home page', async () => {
    await page.goto(STORE_URL);
    await expect(page).toHaveTitle('Gadget Store');
  });

  await test.step('search-backpack: Searching for "backpack"', async () => {
    const searchBox = page.getByRole('searchbox', { name: 'Search products' });
    await searchBox.fill('backpack');
    // Only one product card should be visible containing 'Laptop Backpack'
    const productCards = page.getByRole('listitem').filter({ visible: true });
    await expect(productCards).toHaveCount(1);
    await expect(productCards.first()).toContainText('Laptop Backpack');
  });

  await test.step('clear-search: Clearing the search', async () => {
    const searchBox = page.getByRole('searchbox', { name: 'Search products' });
    await searchBox.clear();
    // All four product cards should be visible again
    const productCards = page.getByRole('listitem').filter({ visible: true });
    await expect(productCards).toHaveCount(4);
  });

  await test.step('add-backpack-to-cart: Adding the Laptop Backpack to the cart', async () => {
    const addButton = page.getByRole('button', { name: 'Add Laptop Backpack to cart' });
    await addButton.click();
    // Cart count should update to 1
    const cartDisplay = page.getByText('1');
    await expect(cartDisplay).toBeVisible();
  });

  await test.step('click-checkout: Clicking Checkout', async () => {
    const checkoutButton = page.getByRole('button', { name: 'Checkout' });
    await checkoutButton.click();
    // After checkout is clicked, the form elements should become visible
    const nameInput = page.getByLabel('Name');
    await expect(nameInput).toBeVisible();
  });

  await test.step('submit-checkout-form: Submitting the form with name "Jane Doe" and email "jane@example.com"', async () => {
    await page.getByLabel('Name').fill('Jane Doe');
    await page.getByLabel('Email').fill('jane@example.com');
    const placeOrderBtn = page.getByRole('button').filter({ hasText: 'Place Order' });
    await expect(placeOrderBtn).toBeVisible();
    await placeOrderBtn.click();
    // Success banner
    const successBanner = page.getByText('Order placed!');
    await expect(successBanner).toBeVisible();
  });
});
